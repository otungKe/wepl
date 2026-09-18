"""Tests for the PaymentIntent coverage report (ADR-0030 Slice A gate).

The report decides whether PaymentIntent can become authoritative for the rail
dimension, so its failure modes matter more than its happy path: an empty
database must not read as "ready", internal (rail-less) movements must not count
as gaps, and an intent that disagrees with the FT must be flagged even though it
technically "covers" it.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ledger.models import FinancialTransaction
from apps.ledger.writer import create_fin_transaction
from apps.payments.coverage import intent_coverage
from apps.payments.models import PaymentIntent

User = get_user_model()


class IntentCoverageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(phone_number="+254700000740")
        self._n = 0

    def _ft(self, **rail):
        self._n += 1
        ft, _ = create_fin_transaction(
            idempotency_key=f"ft-cov-{self._n}",
            op_type=FinancialTransaction.OpType.DISBURSEMENT,
            amount=Decimal("100"), initiated_by=self.user,
            recipient_phone="254700000740",
            initial_state=FinancialTransaction.State.PROCESSING,
        )
        if rail:
            FinancialTransaction.objects.filter(pk=ft.pk).update(**rail)
            ft.refresh_from_db()
        return ft

    def _intent(self, ft, *, provider_ref="", receipt=""):
        self._n += 1
        return PaymentIntent.objects.create(
            provider="mpesa", direction=PaymentIntent.Direction.PAYOUT,
            status=PaymentIntent.Status.SUCCEEDED, amount=Decimal("100"),
            idempotency_key=f"pi-cov-{self._n}", provider_ref=provider_ref,
            receipt=receipt, financial_transaction=ft,
        )

    def test_empty_database_is_no_data_not_ready(self):
        """An empty DB must never green-light the cutover."""
        r = intent_coverage()
        self.assertTrue(r['no_data'])
        self.assertFalse(r['ready_for_cutover'])
        self.assertIsNone(r['coverage_pct'])

    def test_internal_movement_is_not_counted_as_a_gap(self):
        self._ft()  # no rail columns → not rail-backed
        r = intent_coverage()
        self.assertEqual(r['total_rail_backed'], 0)
        self.assertTrue(r['no_data'])

    def test_rail_backed_without_intent_is_uncovered(self):
        ft = self._ft(mpesa_conversation_id="CONV_1")
        r = intent_coverage()
        self.assertEqual(r['total_rail_backed'], 1)
        self.assertEqual(r['uncovered'], 1)
        self.assertEqual(r['coverage_pct'], 0.0)
        self.assertFalse(r['ready_for_cutover'])
        self.assertEqual(r['uncovered_by_op_type'],
                         {FinancialTransaction.OpType.DISBURSEMENT: 1})
        self.assertEqual(r['uncovered_sample'][0]['ft_id'], ft.id)

    def test_full_agreeing_coverage_is_ready(self):
        ft = self._ft(mpesa_conversation_id="CONV_2", mpesa_receipt="RCP_2")
        self._intent(ft, provider_ref="CONV_2", receipt="RCP_2")
        r = intent_coverage()
        self.assertEqual(r['covered'], 1)
        self.assertEqual(r['uncovered'], 0)
        self.assertEqual(r['mismatched'], 0)
        self.assertEqual(r['coverage_pct'], 100.0)
        self.assertTrue(r['ready_for_cutover'])

    def test_disagreeing_intent_is_covered_but_mismatched(self):
        """Coverage without agreement would silently change reads at cutover."""
        ft = self._ft(mpesa_conversation_id="CONV_3", mpesa_receipt="RCP_3")
        self._intent(ft, provider_ref="SOMETHING_ELSE", receipt="RCP_3")
        r = intent_coverage()
        self.assertEqual(r['covered'], 1)
        self.assertEqual(r['mismatched'], 1)
        self.assertFalse(r['ready_for_cutover'])
        self.assertIn("provider_ref", r['mismatch_sample'][0]['problems'][0])

    def test_receipt_only_rail_evidence_counts(self):
        """A collection FT may carry only a receipt — still rail-backed."""
        self._ft(mpesa_receipt="RCP_4")
        r = intent_coverage()
        self.assertEqual(r['total_rail_backed'], 1)
        self.assertEqual(r['uncovered'], 1)

    def test_blank_intent_fields_do_not_count_as_disagreement(self):
        """A best-effort intent with blanks is covered, not mismatched."""
        ft = self._ft(mpesa_conversation_id="CONV_5", mpesa_receipt="RCP_5")
        self._intent(ft, provider_ref="", receipt="")
        r = intent_coverage()
        self.assertEqual(r['covered'], 1)
        self.assertEqual(r['mismatched'], 0)
