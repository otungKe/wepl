"""Payout orchestration (#159).

The payout execution engine moved out of ``apps.ledger.tasks`` into
``apps.payments.payouts``: the ledger is the book of record and must not drive a
rail. These tests pin the behaviour that moved — the dispatch guards, the
provider hand-off, the failure path — plus the boundary itself and the
deploy-window shims for the old task names.
"""
from decimal import Decimal
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.contrib.auth import get_user_model

from apps.core.models import OutboxEvent
from apps.ledger.models import FinancialTransaction
from apps.ledger.money import Money
from apps.ledger.writer import create_fin_transaction
from apps.payments.models import PaymentIntent
from apps.payments.payouts import (
    _query_payout_status, execute_payout, recover_stale_processing_transactions,
)
from apps.payments.providers import StatusResult
from apps.payments.providers.fake import FakeProvider
from apps.payments.providers import registry

User = get_user_model()


def mark_dispatched(ft, provider_ref: str, **over) -> PaymentIntent:
    """Give an FT the rail record a dispatched payout would have.

    The correlation id lives on the intent now (ADR-0030) — FT has no rail
    columns — so a test that needs "this payout was already sent" has to say so
    the way the dispatch path does.
    """
    kwargs = dict(
        provider="fake", direction=PaymentIntent.Direction.PAYOUT,
        amount=ft.amount, idempotency_key=f"pi-payout-{ft.id}",
        provider_ref=provider_ref, financial_transaction=ft,
    )
    kwargs.update(over)
    return PaymentIntent.objects.create(**kwargs)


class _ProviderMixin:
    """Install a FakeProvider for the duration of a test."""

    def use_fake(self, **kwargs) -> FakeProvider:
        provider = FakeProvider(**kwargs)
        registry.use_provider(provider)
        self.addCleanup(registry.use_provider, None)
        return provider


class ExecutePayoutDispatchTests(_ProviderMixin, TestCase):
    def setUp(self):
        self.user = User.objects.create(phone_number="+254700000801")
        self.ft, _ = create_fin_transaction(
            idempotency_key="payout-dispatch-1",
            op_type=FinancialTransaction.OpType.DISBURSEMENT,
            amount=Decimal("500"), initiated_by=self.user,
            recipient_phone="254700000801",
        )

    def test_dispatch_stores_provider_ref_and_leaves_ft_processing(self):
        provider = self.use_fake()
        result = execute_payout(self.ft.id)

        self.ft.refresh_from_db()
        self.assertTrue(result.startswith("dispatched:"))
        self.assertEqual(self.ft.state, FinancialTransaction.State.PROCESSING)
        intent = PaymentIntent.objects.get(financial_transaction=self.ft)
        self.assertEqual(intent.provider_ref, provider.payouts[0]['provider_ref'])

    def test_dispatch_passes_money_and_reference_to_the_provider(self):
        provider = self.use_fake()
        execute_payout(self.ft.id)

        sent = provider.payouts[0]
        self.assertEqual(sent['phone'], "254700000801")
        self.assertEqual(sent['amount'], Money("500"))
        self.assertEqual(sent['reference'], f"WEPL-DISB-{self.ft.id}")

    def test_dispatch_records_the_payment_intent(self):
        self.use_fake()
        execute_payout(self.ft.id)

        intent = PaymentIntent.objects.get(idempotency_key=f"pi-payout-{self.ft.id}")
        self.assertEqual(intent.direction, PaymentIntent.Direction.PAYOUT)
        self.assertEqual(intent.provider, "fake")
        self.assertEqual(intent.amount, Decimal("500"))

    def test_a_rejected_payout_fails_the_ft_and_emits_payment_failed(self):
        self.use_fake(accept=False)
        result = execute_payout(self.ft.id)

        self.ft.refresh_from_db()
        self.assertEqual(result, "no_conversation_id")
        self.assertEqual(self.ft.state, FinancialTransaction.State.FAILED)
        self.assertTrue(OutboxEvent.objects.filter(
            event_type="payment.failed", payload__ft_id=self.ft.id).exists())

    def test_a_rail_error_on_the_last_attempt_fails_the_ft(self):
        provider = self.use_fake()
        # Celery's own way to pose as the final attempt: push a request whose
        # retry count has reached the budget.
        execute_payout.push_request(retries=execute_payout.max_retries)
        self.addCleanup(execute_payout.pop_request)
        with patch.object(provider, "initiate_payout", side_effect=RuntimeError("rail down")):
            result = execute_payout(self.ft.id)

        self.ft.refresh_from_db()
        self.assertEqual(result, "all_retries_exhausted")
        self.assertEqual(self.ft.state, FinancialTransaction.State.FAILED)
        self.assertIn("rail down", self.ft.failure_reason)


class ExecutePayoutGuardTests(_ProviderMixin, TestCase):
    """The dispatch guards are the double-send protection — they must survive
    the move byte-for-byte."""

    def setUp(self):
        self.user = User.objects.create(phone_number="+254700000802")
        self.provider = self.use_fake()

    def _ft(self, key, **kwargs):
        ft, _ = create_fin_transaction(
            idempotency_key=key, op_type=FinancialTransaction.OpType.DISBURSEMENT,
            amount=Decimal("100"), initiated_by=self.user,
            recipient_phone="254700000802", **kwargs)
        return ft

    def test_missing_ft(self):
        self.assertEqual(execute_payout(999999), "not_found")
        self.assertEqual(self.provider.payouts, [])

    def test_already_succeeded(self):
        ft = self._ft("guard-success", initial_state=FinancialTransaction.State.PROCESSING)
        ft.transition_to(FinancialTransaction.State.SUCCESS)
        self.assertEqual(execute_payout(ft.id), "already_succeeded")
        self.assertEqual(self.provider.payouts, [])

    def test_already_failed(self):
        ft = self._ft("guard-failed", initial_state=FinancialTransaction.State.PROCESSING)
        ft.transition_to(FinancialTransaction.State.FAILED)
        self.assertEqual(execute_payout(ft.id), "already_failed")
        self.assertEqual(self.provider.payouts, [])

    def test_already_dispatched(self):
        ft = self._ft("guard-dispatched", initial_state=FinancialTransaction.State.PROCESSING)
        mark_dispatched(ft, "AG_X")
        self.assertEqual(execute_payout(ft.id), "b2c_already_sent")
        self.assertEqual(self.provider.payouts, [])

    def test_a_retry_resumes_from_processing_without_a_transition(self):
        ft = self._ft("guard-retry", initial_state=FinancialTransaction.State.PROCESSING)
        self.assertTrue(execute_payout(ft.id).startswith("dispatched:"))
        self.assertEqual(len(self.provider.payouts), 1)

    def test_unexpected_state_aborts(self):
        ft = self._ft("guard-unexpected", initial_state=FinancialTransaction.State.PROCESSING)
        ft.transition_to(FinancialTransaction.State.SUCCESS)
        FinancialTransaction.objects.filter(pk=ft.pk).update(
            state=FinancialTransaction.State.REVERSED)
        self.assertEqual(execute_payout(ft.id), "unexpected_state")
        self.assertEqual(self.provider.payouts, [])


class QueryPayoutStatusTests(_ProviderMixin, TestCase):
    """Stale recovery asks the rail through the port, never through Daraja."""

    def setUp(self):
        self.user = User.objects.create(phone_number="+254700000803")
        self.ft, _ = create_fin_transaction(
            idempotency_key="requery-1", op_type=FinancialTransaction.OpType.DISBURSEMENT,
            amount=Decimal("100"), initiated_by=self.user,
            recipient_phone="254700000803",
            initial_state=FinancialTransaction.State.PROCESSING,
        )

    def test_no_provider_ref_never_calls_the_rail(self):
        provider = self.use_fake()
        with patch.object(provider, "request_payout_result") as m:
            self.assertEqual(_query_payout_status(self.ft), "UNKNOWN")
        m.assert_not_called()

    def test_maps_the_ports_states(self):
        provider = self.use_fake()
        mark_dispatched(self.ft, "AG_1")
        for state, expected in (("success", "SUCCESS"), ("failed", "FAILED"),
                                ("unknown", "UNKNOWN"), ("pending", "UNKNOWN")):
            with patch.object(provider, "request_payout_result",
                              return_value=StatusResult(state=state)):
                self.assertEqual(_query_payout_status(self.ft), expected)

    def test_a_rail_error_is_unknown_not_a_crash(self):
        provider = self.use_fake()
        mark_dispatched(self.ft, "AG_1")
        with patch.object(provider, "request_payout_result", side_effect=RuntimeError("boom")):
            self.assertEqual(_query_payout_status(self.ft), "UNKNOWN")

    def test_the_default_port_implementation_is_a_no_op(self):
        # FakeProvider inherits it: no rail facility → 'unknown', no exception.
        provider = self.use_fake()
        self.assertEqual(
            provider.request_payout_result(provider_ref="AG_1").state, "unknown")

    def test_recovery_passes_the_ft_reference_to_the_port(self):
        provider = self.use_fake()
        mark_dispatched(self.ft, "AG_1")
        with patch.object(provider, "request_payout_result",
                          return_value=StatusResult(state="unknown")) as m:
            _query_payout_status(self.ft)
        m.assert_called_once_with(
            provider_ref="AG_1", remarks=f"Status query for FT-{self.ft.id}")


class MpesaPayoutRequeryAdapterTests(SimpleTestCase):
    """The Daraja TransactionStatusQuery now lives in the adapter, and still
    reports 'unknown' because Safaricom answers on the callback URL."""

    def test_transaction_status_query_is_accepted_but_inconclusive(self):
        from apps.payments.providers.mpesa import MpesaProvider

        with patch("apps.payments.providers.mpesa.MpesaService._get_access_token",
                   return_value="tok"), \
             patch("requests.post") as post:
            post.return_value.json.return_value = {"ResponseCode": "0"}
            post.return_value.raise_for_status.return_value = None
            res = MpesaProvider().request_payout_result(
                provider_ref="AG_1", remarks="Status query for FT-7")

        self.assertEqual(res.state, "unknown")
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["CommandID"], "TransactionStatusQuery")
        self.assertEqual(body["TransactionID"], "AG_1")
        self.assertEqual(body["Remarks"], "Status query for FT-7")


class LedgerRailBoundaryTests(SimpleTestCase):
    """Module-Boundaries Rule 1 / P-18: the ledger knows nothing of a rail.
    Mirrored by the CI guard so a re-import fails the build, not just this test.
    """

    def _ledger_sources(self):
        from pathlib import Path
        import apps.ledger as ledger_pkg

        root = Path(ledger_pkg.__file__).parent
        return [p for p in root.rglob("*.py")
                if "migrations" not in p.parts and not p.name.startswith("tests")]

    def test_ledger_imports_nothing_from_the_mpesa_app(self):
        offenders = [str(p) for p in self._ledger_sources()
                     if "apps.mpesa" in p.read_text()]
        self.assertEqual(offenders, [], "apps.ledger must not import apps.mpesa")

    def test_ledger_tasks_no_longer_orchestrate_payouts(self):
        import apps.ledger.tasks as ledger_tasks

        for gone in ("execute_b2c_payout", "execute_payout",
                     "recover_stale_processing_transactions",
                     "_handle_payout_failure", "_query_safaricom_status"):
            self.assertFalse(hasattr(ledger_tasks, gone),
                             f"{gone} should have moved to apps.payments.payouts")


class PayoutTaskRegistrationTests(SimpleTestCase):
    """The move must not strand queued work or send it to the wrong queue."""

    def setUp(self):
        from config.celery import app
        self.app = app

    def test_legacy_task_names_still_resolve(self):
        for legacy in ("apps.ledger.tasks.execute_b2c_payout",
                       "apps.ledger.tasks.recover_stale_processing_transactions"):
            self.assertIn(legacy, self.app.tasks)

    def test_the_legacy_shim_requeues_onto_the_new_task(self):
        from apps.payments import payouts

        with patch.object(payouts.execute_payout, "delay") as delay:
            self.assertEqual(payouts._legacy_execute_b2c_payout(42), "requeued")
        delay.assert_called_once_with(42)

    def test_payout_tasks_stay_on_the_financial_queue(self):
        for name in ("apps.payments.payouts.execute_payout",
                     "apps.payments.payouts.recover_stale_processing_transactions"):
            route = self.app.amqp.router.route({}, name)
            self.assertEqual(route["queue"].name, "financial", name)

    def test_the_stk_poller_stays_on_the_payments_queue(self):
        route = self.app.amqp.router.route({}, "apps.payments.tasks.poll_mpesa_stk_status")
        self.assertEqual(route["queue"].name, "payments")
