"""The stale-payout sweep never reverses a payout whose outcome it does not know.

It used to. ``recover_stale_processing_transactions`` asked the rail about any
payout stuck in PROCESSING for an hour, and treated every answer other than
SUCCESS as failure: it failed the payout and the settlement consumer reversed
it, restoring the pool. M-Pesa's status query answers asynchronously, so the
adapter can only ever say ``unknown`` — every stuck M-Pesa payout was reversed,
including the ones Safaricom had paid. The member kept the money and the pool
got it back: a double payout.

These run the real path end to end — a funded pool, a disbursement reserved
through ``post_journal``, dispatch through ``execute_payout`` on the
FakeProvider, the sweep as Celery runs it (no ambient transaction, hence
``TransactionTestCase``), and the inline settlement lane that carries out any
reversal — and read the pool balance at the end, because the harm is to the pool.
"""
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.communities.services import CommunityService
from apps.contributions.services import ContributionService
from apps.core.models import OutboxEvent
from apps.core.tasks import process_inline_deliveries
from apps.ledger import coa, posting_map as pm
from apps.ledger.balances import fund_balance, trial_balance
from apps.ledger.models import FinancialTransaction as FT
from apps.ledger.money import Money
from apps.ledger.posting import post_journal
from apps.ledger.writer import create_fin_transaction
from apps.payments.models import PaymentIntent
from apps.payments.ops import PaymentOpsService
from apps.payments.payouts import execute_payout, recover_stale_processing_transactions
from apps.payments.providers import registry
from apps.payments.providers.fake import FakeProvider
from apps.payments.services import PaymentService

User = get_user_model()


class StalePayoutSweepTests(TransactionTestCase):
    def setUp(self):
        coa.seed_chart_of_accounts()
        self.fake = FakeProvider()
        registry.use_provider(self.fake)
        self.addCleanup(registry.use_provider, None)

        self.admin = User.objects.create(phone_number="+254700000990")
        CommunityService.create_community(self.admin, {"name": "Sweep Pool"})
        self.cid = ContributionService.create_contribution(
            self.admin, {"title": "Sweep fund"}).id
        post_journal(
            idempotency_key="sweep-funding", op_type=pm.Op.CONTRIBUTION,
            lines=pm.contribution_lines(
                member=self.admin, fund_type="contribution",
                fund_id=self.cid, gross=Money("10000")),
        )

    # ── helpers ──────────────────────────────────────────────────────────────
    def _payout(self, key="sweep-1", amount="1000", *, dispatch=True) -> FT:
        """A disbursement whose funds are reserved in the ledger and which has
        (optionally) been handed to the rail, aged past the 60-minute mark."""
        ft, _ = create_fin_transaction(
            idempotency_key=key, op_type=FT.OpType.DISBURSEMENT,
            amount=Decimal(amount), initiated_by=self.admin,
            recipient_phone="254700000990",
        )
        post_journal(
            idempotency_key=f"{key}-journal", op_type=pm.Op.DISBURSEMENT,
            lines=pm.disbursement_lines(
                member=self.admin, fund_type="contribution",
                fund_id=self.cid, amount=Money(amount)),
            financial_transaction=ft,
        )
        if dispatch:
            self.assertTrue(execute_payout(ft.id).startswith("dispatched:"))
        else:
            # Crashed between PROCESSING and the rail's answer: no reference.
            ft.transition_to(FT.State.PROCESSING)
        FT.objects.filter(pk=ft.pk).update(updated_at=timezone.now() - timedelta(hours=2))
        ft.refresh_from_db()
        return ft

    def _ref(self, ft) -> str:
        return PaymentIntent.objects.get(financial_transaction=ft).provider_ref

    def _sweep_and_relay(self) -> dict:
        summary = recover_stale_processing_transactions()
        process_inline_deliveries()   # the settlement consumer: where a reversal lands
        return summary

    def _callback(self, ft, **payload):
        with mock.patch("apps.mpesa.permissions.SafaricomIPPermission.has_permission",
                        return_value=True):
            return APIClient().post(
                "/api/mpesa/b2c/result/",
                {"provider_ref": self._ref(ft), **payload}, format="json")

    # ── the bug ──────────────────────────────────────────────────────────────
    def test_an_unknown_outcome_is_held_not_reversed(self):
        ft = self._payout()
        self.assertEqual(fund_balance("contribution", self.cid), Decimal("9000"))

        summary = self._sweep_and_relay()

        self.assertEqual(summary["needs_review"], 1)
        self.assertEqual(summary["failed"], 0)
        ft.refresh_from_db()
        self.assertEqual(ft.state, FT.State.PROCESSING)
        self.assertFalse(OutboxEvent.objects.filter(event_type="payment.failed").exists())
        # The pool was NOT refunded: Safaricom may well have paid this member.
        self.assertEqual(fund_balance("contribution", self.cid), Decimal("9000"))
        self.assertTrue(trial_balance()["balanced"])

    def test_repeated_sweeps_keep_holding_it(self):
        ft = self._payout()
        for _ in range(3):
            self.assertEqual(self._sweep_and_relay()["needs_review"], 1)
        ft.refresh_from_db()
        self.assertEqual(ft.state, FT.State.PROCESSING)
        self.assertEqual(fund_balance("contribution", self.cid), Decimal("9000"))

    def test_a_payout_with_no_rail_reference_is_held_too(self):
        # The task can die after PROCESSING but before recording the rail's
        # reference, possibly after the rail accepted it. No reference is not
        # evidence that nothing was sent.
        ft = self._payout(dispatch=False)
        self.assertEqual(self._sweep_and_relay()["needs_review"], 1)
        ft.refresh_from_db()
        self.assertEqual(ft.state, FT.State.PROCESSING)
        self.assertEqual(fund_balance("contribution", self.cid), Decimal("9000"))

    # ── how a held payout is resolved ────────────────────────────────────────
    def test_a_late_success_callback_settles_a_held_payout(self):
        ft = self._payout()
        self._sweep_and_relay()

        self.assertEqual(self._callback(ft, success=True, receipt="SWEEPOK01").status_code, 200)
        process_inline_deliveries()

        ft.refresh_from_db()
        self.assertEqual(ft.state, FT.State.SUCCESS)
        self.assertEqual(PaymentIntent.objects.get(financial_transaction=ft).receipt, "SWEEPOK01")
        self.assertEqual(fund_balance("contribution", self.cid), Decimal("9000"))
        self.assertTrue(trial_balance()["balanced"])

    def test_a_late_failure_callback_fails_it_and_restores_the_pool(self):
        ft = self._payout()
        self._sweep_and_relay()

        self._callback(ft, success=False, code="2001", result_desc="declined")
        process_inline_deliveries()

        ft.refresh_from_db()
        self.assertEqual(ft.state, FT.State.FAILED)
        self.assertEqual(fund_balance("contribution", self.cid), Decimal("10000"))
        self.assertTrue(trial_balance()["balanced"])

    def test_an_operator_confirms_it_paid_with_the_receipt(self):
        ft = self._payout()
        self._sweep_and_relay()

        result = PaymentOpsService.confirm_paid(ft, receipt="sweepok02", actor_label="t")
        process_inline_deliveries()

        self.assertEqual(result["outcome"], "healed_success")
        ft.refresh_from_db()
        self.assertEqual(ft.state, FT.State.SUCCESS)
        intent = PaymentIntent.objects.get(financial_transaction=ft)
        self.assertEqual(intent.status, PaymentIntent.Status.SUCCEEDED)
        self.assertEqual(intent.receipt, "SWEEPOK02")
        self.assertEqual(fund_balance("contribution", self.cid), Decimal("9000"))
        # Settled payouts are out of the sweep's reach.
        self.assertEqual(self._sweep_and_relay()["needs_review"], 0)

    def test_confirming_a_payout_with_no_rail_reference_records_the_receipt(self):
        ft = self._payout(dispatch=False)
        PaymentService.record_initiation(
            provider="fake", direction=PaymentIntent.Direction.PAYOUT,
            amount=ft.amount, idempotency_key=f"pi-payout-{ft.id}",
            financial_transaction=ft)
        PaymentOpsService.confirm_paid(ft, receipt="SWEEPOK04")
        intent = PaymentIntent.objects.get(financial_transaction=ft)
        self.assertEqual(intent.status, PaymentIntent.Status.SUCCEEDED)
        self.assertEqual(intent.receipt, "SWEEPOK04")

    def test_an_operator_cannot_confirm_with_another_payments_receipt(self):
        from django.core.exceptions import ValidationError
        paid = self._payout(key="sweep-paid")
        PaymentOpsService.confirm_paid(paid, receipt="SWEEPOK03")
        held = self._payout(key="sweep-held")
        with self.assertRaises(ValidationError):
            PaymentOpsService.confirm_paid(held, receipt="SWEEPOK03")
        held.refresh_from_db()
        self.assertEqual(held.state, FT.State.PROCESSING)

    # ── a rail that does answer ──────────────────────────────────────────────
    def test_a_rail_confirmed_failure_is_still_reversed(self):
        ft = self._payout()
        self.fake.set_status(self._ref(ft), "failed")

        summary = self._sweep_and_relay()

        self.assertEqual(summary["failed"], 1)
        ft.refresh_from_db()
        self.assertEqual(ft.state, FT.State.FAILED)
        self.assertEqual(fund_balance("contribution", self.cid), Decimal("10000"))
        self.assertTrue(trial_balance()["balanced"])

    def test_a_rail_confirmed_success_is_settled(self):
        ft = self._payout()
        self.fake.set_status(self._ref(ft), "success")

        self.assertEqual(self._sweep_and_relay()["settled"], 1)
        ft.refresh_from_db()
        self.assertEqual(ft.state, FT.State.SUCCESS)
        self.assertEqual(fund_balance("contribution", self.cid), Decimal("9000"))

    def test_a_rail_that_errors_is_unknown_not_failure(self):
        ft = self._payout()
        with mock.patch.object(self.fake, "request_payout_result",
                               side_effect=RuntimeError("daraja down")):
            self.assertEqual(self._sweep_and_relay()["needs_review"], 1)
        ft.refresh_from_db()
        self.assertEqual(ft.state, FT.State.PROCESSING)
        self.assertEqual(fund_balance("contribution", self.cid), Decimal("9000"))
