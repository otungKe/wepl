"""Inbound callback views consume normalised CallbackEvents (P1-04)."""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.core.models import OutboxDelivery, OutboxEvent
from apps.ledger.models import FinancialTransaction
from apps.ledger.writer import create_fin_transaction
from apps.mpesa.models import MpesaSTKRequest
from apps.payments.models import PaymentIntent
from apps.payments.providers import registry
from apps.payments.providers.fake import FakeProvider

User = get_user_model()


class STKCallbackViewTests(APITestCase):
    URL = "/api/mpesa/stk/callback/"

    def setUp(self):
        registry.use_provider(FakeProvider())
        self.user = User.objects.create(phone_number="+254700000700")
        self.stk = MpesaSTKRequest.objects.create(
            user=self.user, payment_type="contribution",
            phone_number="254700000700", amount=Decimal("100"),
            checkout_request_id="ws_CO_1", merchant_request_id="m1",
        )

    def tearDown(self):
        registry.use_provider(None)

    def test_success_callback_marks_request_success(self):
        resp = self.client.post(self.URL, {
            "provider_ref": "ws_CO_1", "success": True, "receipt": "QABC123",
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        self.stk.refresh_from_db()
        self.assertEqual(self.stk.status, "SUCCESS")
        self.assertEqual(self.stk.mpesa_receipt, "QABC123")

    def test_failure_callback_marks_request_failed(self):
        resp = self.client.post(self.URL, {
            "provider_ref": "ws_CO_1", "success": False,
            "code": "1032", "result_desc": "cancelled by user",
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        self.stk.refresh_from_db()
        self.assertEqual(self.stk.status, "FAILED")
        self.assertEqual(self.stk.result_code, 1032)

    def test_duplicate_callback_is_idempotent(self):
        MpesaSTKRequest.objects.filter(pk=self.stk.pk).update(status="SUCCESS")
        resp = self.client.post(self.URL, {
            "provider_ref": "ws_CO_1", "success": True, "receipt": "X",
        }, format="json")
        self.assertEqual(resp.status_code, 200)  # no-op, still accepted

    def test_unknown_ref_is_accepted(self):
        resp = self.client.post(self.URL, {
            "provider_ref": "", "success": True,
        }, format="json")
        self.assertEqual(resp.status_code, 200)


class B2CResultViewTests(APITestCase):
    URL = "/api/mpesa/b2c/result/"

    def setUp(self):
        registry.use_provider(FakeProvider())
        self.user = User.objects.create(phone_number="+254700000701")
        self.ft, _ = create_fin_transaction(
            idempotency_key="ft-b2c-1", op_type=FinancialTransaction.OpType.DISBURSEMENT,
            amount=Decimal("500"), initiated_by=self.user, recipient_phone="254700000701",
            initial_state=FinancialTransaction.State.PROCESSING,
        )
        # The dispatch's rail record: the correlation id lives on the intent
        # (ADR-0030), which is what the callback resolves the movement through.
        self.intent = PaymentIntent.objects.create(
            provider="fake", direction=PaymentIntent.Direction.PAYOUT,
            amount=self.ft.amount, idempotency_key=f"pi-payout-{self.ft.id}",
            provider_ref="AG_1", financial_transaction=self.ft)

    def tearDown(self):
        registry.use_provider(None)

    def test_success_marks_ft_success(self):
        resp = self.client.post(self.URL, {
            "provider_ref": "AG_1", "success": True, "receipt": "NLJ7RT61SV",
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        self.ft.refresh_from_db()
        self.assertEqual(self.ft.state, FinancialTransaction.State.SUCCESS)
        self.intent.refresh_from_db()
        self.assertEqual(self.intent.receipt, "NLJ7RT61SV")

    def test_failure_marks_ft_failed(self):
        resp = self.client.post(self.URL, {
            "provider_ref": "AG_1", "success": False, "code": "2001",
            "result_desc": "insufficient funds",
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        self.ft.refresh_from_db()
        self.assertEqual(self.ft.state, FinancialTransaction.State.FAILED)

    def test_unknown_conversation_is_accepted(self):
        resp = self.client.post(self.URL, {
            "provider_ref": "", "success": True,
        }, format="json")
        self.assertEqual(resp.status_code, 200)

    # ── Settlement cutover (ADR-0028): the callback emits a durable event and
    #    defers propagation to the inline consumer instead of finalising inline. ──

    def test_success_emits_settlement_event_and_delivery(self):
        self.client.post(self.URL, {
            "provider_ref": "AG_1", "success": True, "receipt": "NLJ7RT61SV",
        }, format="json")
        ev = OutboxEvent.objects.get(event_type="payment.settled")
        self.assertEqual(ev.payload, {"ft_id": self.ft.id, "receipt": "NLJ7RT61SV"})
        self.assertEqual(ev.dedup_key, f"payment.settled:ft={self.ft.id}")
        self.assertEqual(ev.aggregate_key, f"ft:{self.ft.id}")
        # Fanned out to the inline settlement consumer.
        self.assertTrue(
            OutboxDelivery.objects.filter(
                outbox_event=ev, consumer_name="contributions.settlement").exists())

    def test_failure_emits_failure_event(self):
        self.client.post(self.URL, {
            "provider_ref": "AG_1", "success": False, "code": "2001",
            "result_desc": "insufficient funds",
        }, format="json")
        ev = OutboxEvent.objects.get(event_type="payment.failed")
        self.assertEqual(ev.payload["ft_id"], self.ft.id)
        self.assertIn("2001", ev.payload["reason"])

    def test_success_does_not_finalise_inline(self):
        # Propagation is the consumer's job now — the callback must not call the
        # settlement functions synchronously.
        with patch("apps.contributions.settlement.on_payout_settled") as m:
            self.client.post(self.URL, {
                "provider_ref": "AG_1", "success": True, "receipt": "R",
            }, format="json")
        m.assert_not_called()

    def test_duplicate_callback_emits_only_once(self):
        # First callback wins the transition and emits; a duplicate loses the race
        # (FT already SUCCESS) and emits nothing.
        for _ in range(2):
            self.client.post(self.URL, {
                "provider_ref": "AG_1", "success": True, "receipt": "NLJ7RT61SV",
            }, format="json")
        self.assertEqual(
            OutboxEvent.objects.filter(event_type="payment.settled").count(), 1)
