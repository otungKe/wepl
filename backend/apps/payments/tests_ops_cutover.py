"""Operator-recovery settlement cutover (ADR-0028): the ops heal levers emit
durable settlement events instead of finalising the domain inline. Intent
resolution (_settle_intent) stays synchronous; domain propagation is deferred to
the inline settlement consumer.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.models import OutboxDelivery, OutboxEvent
from apps.ledger.models import FinancialTransaction
from apps.ledger.writer import create_fin_transaction
from apps.payments.ops import PaymentOpsService

User = get_user_model()


class OpsCutoverTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(phone_number="+254700000712")
        self.ft, _ = create_fin_transaction(
            idempotency_key="ft-ops-1", op_type=FinancialTransaction.OpType.DISBURSEMENT,
            amount=Decimal("500"), initiated_by=self.user, recipient_phone="254700000712",
            initial_state=FinancialTransaction.State.PROCESSING,
        )

    def test_apply_success_emits_settlement_event(self):
        PaymentOpsService._apply_success(self.ft, actor_label="tester")
        self.ft.refresh_from_db()
        self.assertEqual(self.ft.state, FinancialTransaction.State.SUCCESS)
        ev = OutboxEvent.objects.get(event_type="payment.settled")
        self.assertEqual(ev.payload, {"ft_id": self.ft.id, "receipt": ""})
        self.assertTrue(OutboxDelivery.objects.filter(
            outbox_event=ev, consumer_name="contributions.settlement").exists())

    def test_apply_failure_emits_failure_event(self):
        PaymentOpsService._apply_failure(self.ft, reason="ops forced fail", actor_label="tester")
        self.ft.refresh_from_db()
        self.assertEqual(self.ft.state, FinancialTransaction.State.FAILED)
        ev = OutboxEvent.objects.get(event_type="payment.failed")
        self.assertEqual(ev.payload["ft_id"], self.ft.id)
        self.assertIn("ops forced fail", ev.payload["reason"])

    def test_apply_failure_defers_reversal_to_the_consumer(self):
        from unittest.mock import patch
        with patch("apps.ledger.posting.reverse_financial_transaction") as rev:
            PaymentOpsService._apply_failure(self.ft, reason="x", actor_label="t")
        rev.assert_not_called()
