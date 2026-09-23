"""PaymentIntent becomes authoritative for the rail dimension (ADR-0030).

FT's ``mpesa_*`` columns are written on the payout path only, and ADR-0030 drops
them. Before that can happen the intent has to be the thing every reader
consults and every dispatch records — not a best-effort shadow written after the
money already moved. These tests pin that inversion: the intent exists before
the rail is called, the correlation id lands on it, and the callback, the
operator levers and the stale sweep all find the movement through it.
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

    def test_the_double_send_guard_reads_the_intent_not_the_column(self):
        ft = self._ft(initial_state=FinancialTransaction.State.PROCESSING)
        PaymentIntent.objects.create(
            provider="fake", direction=PaymentIntent.Direction.PAYOUT,
            amount=ft.amount, idempotency_key="pi-elsewhere",
            provider_ref="ALREADY_SENT", financial_transaction=ft)
        # FT's own column is empty — only the intent knows it was dispatched.
        self.assertEqual(execute_payout(ft.id), "b2c_already_sent")
        self.assertEqual(self.provider.payouts, [])


class RailLookupTests(_PayoutCase):
    def test_a_correlation_id_resolves_to_its_movement_through_the_intent(self):
        ft = self._ft()
        execute_payout(ft.id)
        ref = self.provider.payouts[0]["provider_ref"]
        # Clear the legacy column so only the intent can answer.
        FinancialTransaction.objects.filter(pk=ft.pk).update(mpesa_conversation_id=None)
        found = money_activity.financial_transaction_for_ref(ref, provider="fake")
        self.assertEqual(found.id, ft.id)

    def test_a_legacy_row_with_no_intent_still_resolves_from_the_column(self):
        ft = self._ft(key="rail-auth-legacy")
        FinancialTransaction.objects.filter(pk=ft.pk).update(
            mpesa_conversation_id="AG_LEGACY")
        found = money_activity.financial_transaction_for_ref("AG_LEGACY")
        self.assertEqual(found.id, ft.id)

    def test_an_unknown_reference_resolves_to_nothing(self):
        self.assertIsNone(money_activity.financial_transaction_for_ref("AG_NOBODY"))
        self.assertIsNone(money_activity.financial_transaction_for_ref(""))

    def test_rail_info_prefers_the_intent_over_the_column(self):
        ft = self._ft()
        execute_payout(ft.id)
        ref = self.provider.payouts[0]["provider_ref"]
        FinancialTransaction.objects.filter(pk=ft.pk).update(
            mpesa_conversation_id="STALE_COLUMN")
        ft.refresh_from_db()
        self.assertEqual(money_activity.rail_for(ft).conversation_id, ref)


class BackfillMigrationTests(TestCase):
    """The data migration's logic, exercised against the live models — the
    columns still exist, so the same two branches apply."""

    def setUp(self):
        self.user = User.objects.create(phone_number="+254700000902")

    def _ft(self, key, **columns):
        ft, _ = create_fin_transaction(
            idempotency_key=key, op_type=FinancialTransaction.OpType.DISBURSEMENT,
            amount=Decimal("400"), initiated_by=self.user,
            recipient_phone="254700000902")
        if columns:
            FinancialTransaction.objects.filter(pk=ft.pk).update(**columns)
            ft.refresh_from_db()
        return ft

    def _run(self):
        # The migration module's name starts with a digit, so it is imported by
        # path rather than with a plain `from ... import`.
        import importlib

        from django.apps import apps as django_apps
        mod = importlib.import_module(
            "apps.payments.migrations.0008_backfill_payout_intents")
        mod.backfill(django_apps, None)

    def test_an_unlinked_intent_is_attached_rather_than_duplicated(self):
        ft = self._ft("bf-link", mpesa_conversation_id="AG_LINK")
        PaymentIntent.objects.create(
            provider="mpesa", direction=PaymentIntent.Direction.PAYOUT,
            amount=ft.amount, idempotency_key="pi-orphan", provider_ref="AG_LINK")
        self._run()
        self.assertEqual(PaymentIntent.objects.filter(provider_ref="AG_LINK").count(), 1)
        self.assertEqual(
            PaymentIntent.objects.get(provider_ref="AG_LINK").financial_transaction_id,
            ft.id)

    def test_a_movement_with_no_intent_gets_one_minted_from_its_columns(self):
        ft = self._ft("bf-mint", mpesa_conversation_id="AG_MINT",
                      mpesa_receipt="RCP_MINT")
        self._run()
        intent = PaymentIntent.objects.get(idempotency_key=f"pi-payout-{ft.id}")
        self.assertEqual(intent.provider_ref, "AG_MINT")
        self.assertEqual(intent.receipt, "RCP_MINT")
        self.assertEqual(intent.financial_transaction_id, ft.id)
        self.assertEqual(intent.amount, ft.amount)

    def test_running_it_twice_changes_nothing(self):
        ft = self._ft("bf-idem", mpesa_conversation_id="AG_IDEM")
        self._run()
        self._run()
        self.assertEqual(PaymentIntent.objects.filter(financial_transaction=ft).count(), 1)

    def test_a_movement_with_no_rail_columns_is_left_alone(self):
        ft = self._ft("bf-internal")
        self._run()
        self.assertFalse(PaymentIntent.objects.filter(financial_transaction=ft).exists())
