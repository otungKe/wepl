"""Tests for the money-activity read projection (ADR-0030).

Cover the "prefer PaymentIntent, fall back to FT columns" rail logic that lets
readers migrate off FinancialTransaction without losing data.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ledger import money_activity
from apps.ledger.models import FinancialTransaction
from apps.ledger.writer import create_fin_transaction
from apps.payments.models import PaymentIntent

User = get_user_model()


class MoneyActivityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(phone_number="+254700000730")
        self.ft, _ = create_fin_transaction(
            idempotency_key="ft-ma-1", op_type=FinancialTransaction.OpType.DISBURSEMENT,
            amount=Decimal("500"), initiated_by=self.user, recipient_phone="254700000730",
            initial_state=FinancialTransaction.State.PROCESSING,
        )

    def _intent(self, **over):
        kwargs = dict(
            provider="mpesa", direction=PaymentIntent.Direction.PAYOUT,
            status=PaymentIntent.Status.SUCCEEDED, amount=Decimal("500"),
            idempotency_key="pi-ma-1", provider_ref="AG_CONV_1", receipt="RCP1",
            financial_transaction=self.ft,
        )
        kwargs.update(over)
        return PaymentIntent.objects.create(**kwargs)

    def test_basic_fields_and_reference(self):
        ma = money_activity.for_financial_transaction(self.ft)
        self.assertEqual(ma.reference, self.ft.reference)
        self.assertEqual(ma.reference, f"WEPL-TXN-{self.ft.id:06d}")
        self.assertEqual(ma.op_type, FinancialTransaction.OpType.DISBURSEMENT)
        self.assertEqual(ma.amount, Decimal("500"))
        self.assertEqual(ma.state, FinancialTransaction.State.PROCESSING)
        self.assertEqual(ma.recipient_phone, "254700000730")

    def test_rail_prefers_payout_intent(self):
        self._intent()
        ma = money_activity.for_financial_transaction(self.ft)
        self.assertEqual(ma.rail.provider, "mpesa")
        self.assertEqual(ma.rail.direction, PaymentIntent.Direction.PAYOUT)
        self.assertEqual(ma.rail.status, PaymentIntent.Status.SUCCEEDED)
        self.assertEqual(ma.rail.conversation_id, "AG_CONV_1")   # payout → provider_ref
        self.assertEqual(ma.rail.checkout_id, "")
        self.assertEqual(ma.rail.receipt, "RCP1")
        self.assertTrue(ma.rail.has_rail)

    def test_rail_prefers_collection_intent(self):
        self._intent(direction=PaymentIntent.Direction.COLLECTION, provider_ref="ws_CO_9")
        ma = money_activity.for_financial_transaction(self.ft)
        self.assertEqual(ma.rail.checkout_id, "ws_CO_9")         # collection → provider_ref
        self.assertEqual(ma.rail.conversation_id, "")

    def test_receipt_falls_back_to_ft_when_intent_blank(self):
        FinancialTransaction.objects.filter(pk=self.ft.pk).update(mpesa_receipt="FTRCP")
        self.ft.refresh_from_db()
        self._intent(receipt="")
        ma = money_activity.for_financial_transaction(self.ft)
        self.assertEqual(ma.rail.receipt, "FTRCP")

    def test_falls_back_to_ft_columns_without_intent(self):
        FinancialTransaction.objects.filter(pk=self.ft.pk).update(
            mpesa_conversation_id="FTCONV", mpesa_receipt="FTRCP")
        self.ft.refresh_from_db()
        ma = money_activity.for_financial_transaction(self.ft)
        self.assertEqual(ma.rail.conversation_id, "FTCONV")
        self.assertEqual(ma.rail.receipt, "FTRCP")
        self.assertEqual(ma.rail.provider, "mpesa")

    def test_no_rail_for_internal_movement(self):
        ma = money_activity.for_financial_transaction(self.ft)
        self.assertFalse(ma.rail.has_rail)
        self.assertEqual(ma.rail.provider, "")

    def test_latest_intent_wins(self):
        self._intent(idempotency_key="pi-old", provider_ref="OLD", receipt="OLD_R")
        self._intent(idempotency_key="pi-new", provider_ref="NEW", receipt="NEW_R")
        ma = money_activity.for_financial_transaction(self.ft)
        self.assertEqual(ma.rail.conversation_id, "NEW")
        self.assertEqual(ma.rail.receipt, "NEW_R")

    def test_prefetch_cache_avoids_a_query_per_row(self):
        """List callers prefetch payment_intents; the seam must not re-query."""
        self._intent()
        second, _ = create_fin_transaction(
            idempotency_key="ft-ma-2", op_type=FinancialTransaction.OpType.DISBURSEMENT,
            amount=Decimal("100"), initiated_by=self.user, recipient_phone="254700000731",
            initial_state=FinancialTransaction.State.PROCESSING,
        )
        PaymentIntent.objects.create(
            provider="mpesa", direction=PaymentIntent.Direction.PAYOUT,
            status=PaymentIntent.Status.SUCCEEDED, amount=Decimal("100"),
            idempotency_key="pi-ma-2", provider_ref="AG_CONV_2", receipt="RCP2",
            financial_transaction=second,
        )
        qs = FinancialTransaction.objects.prefetch_related("payment_intents")
        # 1 query for the transactions + 1 for the prefetch; none per row.
        with self.assertNumQueries(2):
            refs = [money_activity.for_financial_transaction(ft).rail.conversation_id
                    for ft in qs]
        self.assertCountEqual(refs, ["AG_CONV_1", "AG_CONV_2"])
