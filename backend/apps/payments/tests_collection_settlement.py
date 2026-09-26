"""A settled pay-in travels as a durable ``payment.settled`` event keyed by its
PaymentIntent, not as an ``on_commit`` call off the M-Pesa rail record.

``TransactionTestCase`` throughout: the credit happens in an ``on_commit``
callback and a relay run, and the ledger's balance trigger fires at COMMIT —
a ``TestCase`` would hide all three (see the wepl-testing skill).
"""
from decimal import Decimal
from unittest.mock import patch

from django.test import TransactionTestCase
from rest_framework.test import APIClient

from apps.contributions.tests import approve_kyc, make_contribution, make_user
from apps.core.models import OutboxDelivery, OutboxEvent
from apps.core.tasks import process_inline_deliveries
from apps.ledger import coa
from apps.ledger.balances import trial_balance
from apps.ledger.models import FinancialTransaction as FT
from apps.mpesa.models import MpesaSTKRequest
from apps.payments.collection import start_collection
from apps.payments.models import PaymentIntent
from apps.payments.providers import registry
from apps.payments.providers.fake import FakeProvider

CALLBACK = "/api/mpesa/stk/callback/"


class CollectionSettlesThroughTheEventTests(TransactionTestCase):

    def setUp(self):
        coa.seed_chart_of_accounts()
        registry.use_provider(FakeProvider())
        self.payer = make_user("254700000810")
        approve_kyc(self.payer)
        self.contribution = make_contribution(self.payer)
        self.client = APIClient()

    def tearDown(self):
        registry.use_provider(None)

    def _start(self, amount="250.00"):
        started = start_collection(
            user=self.payer, phone=self.payer.phone_number, amount=Decimal(amount),
            reference=f"WEPL-{self.contribution.id}", description="Test Pool",
            payment_type="contribution", contribution_id=self.contribution.id,
        )
        self.assertTrue(started.accepted)
        return started.provider_ref

    def _callback(self, ref, receipt="QREC1"):
        resp = self.client.post(CALLBACK, {
            "provider_ref": ref, "success": True, "receipt": receipt,
        }, format="json")
        self.assertEqual(resp.status_code, 200)

    def _credits(self):
        return FT.objects.filter(op_type=FT.OpType.CONTRIBUTION,
                                 contribution=self.contribution)

    def test_the_intent_records_what_the_payin_is_for(self):
        ref = self._start()
        intent = PaymentIntent.objects.get(provider_ref=ref)
        self.assertEqual(intent.purpose, "contribution")
        self.assertEqual(intent.subject_ref, str(self.contribution.id))
        self.assertEqual(intent.initiated_by, self.payer)

    def test_callback_emits_one_event_and_credits_before_answering(self):
        ref = self._start()
        self._callback(ref)

        intent = PaymentIntent.objects.get(provider_ref=ref)
        event = OutboxEvent.objects.get(event_type="payment.settled")
        self.assertEqual(event.payload, {"intent_id": intent.id, "receipt": "QREC1"})
        self.assertEqual(
            OutboxDelivery.objects.get(outbox_event=event).status,
            OutboxDelivery.Status.PROCESSED)
        credit = self._credits().get()
        self.assertEqual(credit.amount, Decimal("250.00"))
        self.assertEqual(credit.initiated_by, self.payer)
        self.assertTrue(trial_balance()["balanced"])

    def test_duplicate_callback_credits_once(self):
        ref = self._start()
        self._callback(ref)
        self._callback(ref)
        self.assertEqual(OutboxEvent.objects.filter(event_type="payment.settled").count(), 1)
        self.assertEqual(self._credits().count(), 1)

    def test_redelivering_the_event_credits_once(self):
        # At-least-once delivery: the consumer must tolerate the same fact twice.
        from apps.contributions.settlement_consumer import handle_settlement
        ref = self._start()
        self._callback(ref)
        handle_settlement(OutboxEvent.objects.get(event_type="payment.settled"))
        self.assertEqual(self._credits().count(), 1)
        self.assertTrue(trial_balance()["balanced"])

    def test_the_relay_credits_when_immediate_delivery_does_not_run(self):
        ref = self._start()
        with patch("apps.payments.views_mpesa._deliver_now"):
            self._callback(ref)
        self.assertFalse(self._credits().exists())    # durable, not yet delivered

        process_inline_deliveries()
        self.assertEqual(self._credits().count(), 1)

    def test_a_payin_already_credited_off_the_rail_record_is_not_credited_again(self):
        # Mid-deploy: the old instance credited this checkout through the rail
        # record. The same fact arriving as an event must hit the same keys.
        from apps.contributions import settlement
        ref = self._start()
        settlement.on_collection_settled(
            payment_type="contribution", user=self.payer, amount=Decimal("250.00"),
            receipt="QREC1", contribution_id=self.contribution.id,
            idempotency_seed=ref)
        self._callback(ref, receipt="QREC1")
        self.assertEqual(self._credits().count(), 1)

    def test_an_intent_that_does_not_say_what_it_is_for_falls_back_to_the_rail_record(self):
        ref = self._start()
        PaymentIntent.objects.filter(provider_ref=ref).update(purpose="", subject_ref="")

        self._callback(ref)

        self.assertFalse(OutboxEvent.objects.filter(event_type="payment.settled").exists())
        self.assertEqual(MpesaSTKRequest.objects.get(checkout_request_id=ref).status, "SUCCESS")
        self.assertEqual(self._credits().count(), 1)
