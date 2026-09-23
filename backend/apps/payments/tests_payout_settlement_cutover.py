"""Payout-task settlement cutover (ADR-0028): the payout-failure path and the
stale-recovery success path emit durable settlement events instead of finalising
inline. Propagation (ledger reversal, domain reset/advance, notify) is deferred to
the inline settlement consumer.
"""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.core.models import OutboxDelivery, OutboxEvent
from apps.ledger.models import FinancialTransaction
from apps.payments.payouts import (
    _handle_payout_failure, recover_stale_processing_transactions,
)
from apps.ledger.writer import create_fin_transaction
from apps.payments.models import PaymentIntent

User = get_user_model()


class HandlePayoutFailureCutoverTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(phone_number="+254700000710")
        self.ft, _ = create_fin_transaction(
            idempotency_key="ft-fail-1", op_type=FinancialTransaction.OpType.DISBURSEMENT,
            amount=Decimal("500"), initiated_by=self.user, recipient_phone="254700000710",
            initial_state=FinancialTransaction.State.PROCESSING,
        )

    def test_failure_transitions_failed_and_emits_event(self):
        _handle_payout_failure(self.ft, "rail declined")
        self.ft.refresh_from_db()
        self.assertEqual(self.ft.state, FinancialTransaction.State.FAILED)
        ev = OutboxEvent.objects.get(event_type="payment.failed")
        self.assertEqual(ev.payload["ft_id"], self.ft.id)
        self.assertIn("rail declined", ev.payload["reason"])
        self.assertTrue(OutboxDelivery.objects.filter(
            outbox_event=ev, consumer_name="contributions.settlement").exists())

    def test_failure_defers_reversal_to_the_consumer(self):
        # The reversal now runs in the consumer, not inline in the task.
        with patch("apps.ledger.posting.reverse_financial_transaction") as rev:
            _handle_payout_failure(self.ft, "rail declined")
        rev.assert_not_called()

    def test_failure_is_idempotent_when_already_terminal(self):
        self.ft.transition_to(FinancialTransaction.State.FAILED)
        _handle_payout_failure(self.ft, "second call")
        # Lost the race → no event emitted by this path.
        self.assertFalse(OutboxEvent.objects.filter(event_type="payment.failed").exists())


class StaleRecoverySuccessCutoverTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(phone_number="+254700000711")
        self.ft, _ = create_fin_transaction(
            idempotency_key="ft-stale-1", op_type=FinancialTransaction.OpType.DISBURSEMENT,
            amount=Decimal("500"), initiated_by=self.user, recipient_phone="254700000711",
            initial_state=FinancialTransaction.State.PROCESSING,
        )
        # The dispatch's rail record — the correlation id lives on the intent
        # (ADR-0030), which is where the sweep reads it from.
        PaymentIntent.objects.create(
            provider="fake", direction=PaymentIntent.Direction.PAYOUT,
            amount=self.ft.amount, idempotency_key=f"pi-payout-{self.ft.id}",
            provider_ref="AG_STALE", financial_transaction=self.ft)
        # Age it past the 60-min auto-recover threshold.
        FinancialTransaction.objects.filter(pk=self.ft.pk).update(
            updated_at=timezone.now() - timedelta(hours=2),
        )

    def test_safaricom_confirmed_success_emits_settlement_event(self):
        with patch("apps.payments.payouts._query_payout_status", return_value="SUCCESS"):
            result = recover_stale_processing_transactions()
        self.assertEqual(result["recovered"], 1)
        self.ft.refresh_from_db()
        self.assertEqual(self.ft.state, FinancialTransaction.State.SUCCESS)
        ev = OutboxEvent.objects.get(event_type="payment.settled")
        self.assertEqual(ev.payload["ft_id"], self.ft.id)
        self.assertTrue(OutboxDelivery.objects.filter(
            outbox_event=ev, consumer_name="contributions.settlement").exists())
