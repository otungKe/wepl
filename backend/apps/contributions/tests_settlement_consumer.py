"""Tests for the inline settlement consumer (ADR-0028 propagation, ADR-0029 Stage 2).

The consumer is registered at app startup; here we verify its routing and that a
fanned-out delivery runs it end-to-end via the inline relay. Propagation targets
(on_payout_settled / on_payout_failed / reverse_financial_transaction) are proven
elsewhere, so they're patched to keep these tests about the consumer's wiring.
"""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.contributions.settlement_consumer import CONSUMER_NAME, handle_settlement
from apps.core.events import _INLINE_CONSUMERS, emit_event
from apps.core.models import OutboxDelivery
from apps.core.tasks import process_inline_deliveries
from apps.ledger.models import FinancialTransaction

User = get_user_model()


class SettlementConsumerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(phone_number="+254700000700")
        self.ft = FinancialTransaction.objects.create(
            op_type=FinancialTransaction.OpType.DISBURSEMENT,
            amount=Decimal("100.00"),
            idempotency_key="settle-test-1",
            initiated_by=self.user,
        )

    def test_consumer_is_registered_for_the_two_settlement_events(self):
        self.assertIn(CONSUMER_NAME, _INLINE_CONSUMERS)
        self.assertEqual(
            _INLINE_CONSUMERS[CONSUMER_NAME].event_types,
            frozenset({"payment.settled", "payment.failed"}),
        )

    def test_settled_routes_to_on_payout_settled(self):
        ev = emit_event("payment.settled",
                        body={"ft_id": self.ft.id, "receipt": "RCP1"})
        with patch("apps.contributions.settlement.on_payout_settled") as m:
            handle_settlement(ev)
        m.assert_called_once()
        called_ft, called_receipt = m.call_args[0]
        self.assertEqual(called_ft.id, self.ft.id)
        self.assertEqual(called_receipt, "RCP1")

    def test_failed_routes_to_reverse_then_on_payout_failed(self):
        ev = emit_event("payment.failed",
                        body={"ft_id": self.ft.id, "reason": "rail declined"})
        with patch("apps.ledger.posting.reverse_financial_transaction") as rev, \
             patch("apps.contributions.settlement.on_payout_failed") as failed:
            handle_settlement(ev)
        rev.assert_called_once()
        failed.assert_called_once()

    def test_missing_ft_id_raises(self):
        ev = emit_event("payment.settled", body={})
        with self.assertRaises(ValueError):
            handle_settlement(ev)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
    def test_end_to_end_delivery_runs_propagation(self):
        with patch("apps.contributions.settlement.on_payout_settled") as m:
            emit_event(
                "payment.settled",
                aggregate_key=f"ft:{self.ft.id}",
                dedup_key=f"payment.settled:ft={self.ft.id}",
                body={"ft_id": self.ft.id, "receipt": "RCP2"},
            )
            # A delivery row was fanned out for the registered consumer.
            d = OutboxDelivery.objects.get(consumer_name=CONSUMER_NAME)
            self.assertEqual(d.status, OutboxDelivery.Status.PENDING)
            result = process_inline_deliveries()
        self.assertEqual(result, {"processed": 1, "dead": 0})
        d.refresh_from_db()
        self.assertEqual(d.status, OutboxDelivery.Status.PROCESSED)
        m.assert_called_once()
