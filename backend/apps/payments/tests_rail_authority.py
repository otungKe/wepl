"""PaymentIntent becomes authoritative for the rail dimension (ADR-0030).

FT's ``mpesa_*`` columns were written on the payout path only, and ADR-0030 has
now dropped them. The intent had first to become the thing every reader consults
and every dispatch records — not a best-effort shadow written after the money
already moved. These tests pin that inversion: the intent exists before the rail
is called, the correlation id lands on it, and the callback, the operator levers
and the stale sweep all find the movement through it.

The backfill that carried the columns' values into intents
(``payments.0008``) was exercised against the live models while they still
existed. Its inputs cannot be constructed any more, so those tests went with the
columns; the migration itself stays in the chain and is a no-op on a database
that never had them.
"""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ledger.models import FinancialTransaction
from apps.ledger.writer import create_fin_transaction
from apps.payments import money_activity
from apps.payments.models import PaymentIntent
from apps.payments.payouts import execute_payout
from apps.payments.providers import registry
from apps.payments.providers.fake import FakeProvider

User = get_user_model()


class _PayoutCase(TestCase):
    def setUp(self):
        self.user = User.objects.create(phone_number="+254700000901")
        self.provider = FakeProvider()
        registry.use_provider(self.provider)
        self.addCleanup(registry.use_provider, None)

    def _ft(self, key="rail-auth-1", **kwargs):
        ft, _ = create_fin_transaction(
            idempotency_key=key, op_type=FinancialTransaction.OpType.DISBURSEMENT,
            amount=Decimal("750"), initiated_by=self.user,
            recipient_phone="254700000901", **kwargs)
        return ft


class IntentIsRecordedBeforeDispatchTests(_PayoutCase):
    def test_the_intent_exists_even_when_the_rail_call_blows_up(self):
        ft = self._ft()
        with patch.object(self.provider, "initiate_payout",
                          side_effect=RuntimeError("rail down")):
            execute_payout.push_request(retries=execute_payout.max_retries)
            self.addCleanup(execute_payout.pop_request)
            execute_payout(ft.id)

        intent = PaymentIntent.objects.get(idempotency_key=f"pi-payout-{ft.id}")
        self.assertEqual(intent.financial_transaction_id, ft.id)
        self.assertEqual(intent.provider_ref, "")

    def test_a_failed_intent_write_stops_the_payout_before_the_rail(self):
        # Recording is no longer swallowed: if the rail record cannot be made,
        # no money is sent.
        ft = self._ft()
        with patch("apps.payments.services.PaymentService.record_initiation",
                   side_effect=RuntimeError("db down")):
            with self.assertRaises(RuntimeError):
                execute_payout(ft.id)
        self.assertEqual(self.provider.payouts, [])

    def test_dispatch_puts_the_correlation_id_on_the_intent(self):
        ft = self._ft()
        execute_payout(ft.id)
        intent = PaymentIntent.objects.get(idempotency_key=f"pi-payout-{ft.id}")
        self.assertEqual(intent.provider_ref, self.provider.payouts[0]["provider_ref"])

    def test_a_retry_reuses_the_same_intent(self):
        ft = self._ft(initial_state=FinancialTransaction.State.PROCESSING)
        execute_payout(ft.id)
        execute_payout(ft.id)      # second pass: guard should stop it
        self.assertEqual(
            PaymentIntent.objects.filter(financial_transaction=ft).count(), 1)
        self.assertEqual(len(self.provider.payouts), 1)

    def test_the_double_send_guard_reads_the_intent(self):
        ft = self._ft(initial_state=FinancialTransaction.State.PROCESSING)
        PaymentIntent.objects.create(
            provider="fake", direction=PaymentIntent.Direction.PAYOUT,
            amount=ft.amount, idempotency_key="pi-elsewhere",
            provider_ref="ALREADY_SENT", financial_transaction=ft)
        # The intent is the only record that this payout already went out.
        self.assertEqual(execute_payout(ft.id), "b2c_already_sent")
        self.assertEqual(self.provider.payouts, [])


class RailLookupTests(_PayoutCase):
    def test_a_correlation_id_resolves_to_its_movement_through_the_intent(self):
        ft = self._ft()
        execute_payout(ft.id)
        ref = self.provider.payouts[0]["provider_ref"]
        found = money_activity.financial_transaction_for_ref(ref, provider="fake")
        self.assertEqual(found.id, ft.id)

    def test_a_movement_with_no_intent_cannot_be_reached_by_reference(self):
        """There is no column left to fall back to: no intent, no rail identity."""
        self._ft(key="rail-auth-no-intent")
        self.assertIsNone(money_activity.financial_transaction_for_ref("AG_NOTHING"))

    def test_an_unknown_reference_resolves_to_nothing(self):
        self.assertIsNone(money_activity.financial_transaction_for_ref("AG_NOBODY"))
        self.assertIsNone(money_activity.financial_transaction_for_ref(""))

    def test_rail_info_reads_the_intent(self):
        ft = self._ft()
        execute_payout(ft.id)
        ref = self.provider.payouts[0]["provider_ref"]
        self.assertEqual(money_activity.rail_for(ft).conversation_id, ref)

    def test_an_ft_with_no_intent_has_no_rail(self):
        ft = self._ft(key="rail-auth-internal")
        rail = money_activity.rail_for(ft)
        self.assertFalse(rail.has_rail)
        self.assertEqual(rail.conversation_id, "")
        self.assertEqual(rail.receipt, "")
