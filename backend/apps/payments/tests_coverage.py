"""Tests for the PaymentIntent coverage report (ADR-0030 Slice A gate).

The report decides whether PaymentIntent can become authoritative for the rail
dimension, so its failure modes matter more than its happy path: an empty
database must not read as "ready" and internal (rail-less) movements must not
count as gaps.

Above all it must see the **collection** side. The report's first version looked
for FT's ``mpesa_*`` columns, which were written on the payout path only, so it
measured the one subset that was covered by construction and called a database
with no collection coverage at all "100% ready". Those columns are gone now
(ADR-0030) and the rail leg is read from the journal, which no missing column
can hide; the collection tests below keep that regression from coming back.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ledger import coa, posting_map as pm
from apps.ledger.models import FinancialTransaction
from apps.ledger.money import Money
from apps.ledger.posting import post_journal
from apps.ledger.writer import create_fin_transaction
from apps.payments.coverage import (
    NEEDS_BACKFILL, NEEDS_REVIEW, READY, intent_coverage, receipt_hint,
)
from apps.payments.models import PaymentIntent

User = get_user_model()


class IntentCoverageTests(TestCase):
    def setUp(self):
        coa.seed_chart_of_accounts()
        self.user = User.objects.create(phone_number="+254700000740")
        self._n = 0

    def _ft(self, *, with_journal=True):
        """A payout movement. Rail-backed means its journal moved money across
        the boundary — FT carries no rail columns to say so (ADR-0030)."""
        self._n += 1
        key = f"ft-cov-{self._n}"
        ft, _ = create_fin_transaction(
            idempotency_key=key,
            op_type=FinancialTransaction.OpType.DISBURSEMENT,
            amount=Decimal("100"), initiated_by=self.user,
            recipient_phone="254700000740",
            initial_state=FinancialTransaction.State.PROCESSING,
        )
        if with_journal:
            post_journal(
                idempotency_key=f"je-{key}", op_type=pm.Op.DISBURSEMENT,
                lines=pm.disbursement_lines(
                    member=self.user, fund_type="contribution", fund_id=1,
                    amount=Money("100")),
                financial_transaction=ft, created_by=self.user,
            )
        return ft

    def _intent(self, ft, *, provider_ref="", receipt=""):
        self._n += 1
        return PaymentIntent.objects.create(
            provider="mpesa", direction=PaymentIntent.Direction.PAYOUT,
            status=PaymentIntent.Status.SUCCEEDED, amount=Decimal("100"),
            idempotency_key=f"pi-cov-{self._n}", provider_ref=provider_ref,
            receipt=receipt, financial_transaction=ft,
        )

    def _collection_ft(self, *, idempotency_key, amount="500"):
        """An FT posted the way a real pay-in is: a journal into M-Pesa float and
        no rail columns whatsoever (``create_fin_transaction`` takes none)."""
        ft, _ = create_fin_transaction(
            idempotency_key=idempotency_key,
            op_type=FinancialTransaction.OpType.CONTRIBUTION,
            amount=Decimal(amount), initiated_by=self.user,
            initial_state=FinancialTransaction.State.SUCCESS,
        )
        post_journal(
            idempotency_key=f"je-{idempotency_key}",
            op_type=pm.Op.CONTRIBUTION,
            lines=pm.contribution_lines(
                member=self.user, fund_type="contribution", fund_id=1,
                gross=Money(amount)),
            financial_transaction=ft,
            created_by=self.user,
        )
        return ft

    def _orphan_collection_intent(self, *, provider_ref, receipt):
        """What the STK chokepoint actually mints: an intent with no FT, because
        the FT does not exist yet at initiation and nothing links it later."""
        return PaymentIntent.objects.create(
            provider="mpesa", direction=PaymentIntent.Direction.COLLECTION,
            status=PaymentIntent.Status.SUCCEEDED, amount=Decimal("500"),
            idempotency_key=f"pi-collect-{provider_ref}",
            provider_ref=provider_ref, receipt=receipt,
        )

    # ── the empty / internal cases ───────────────────────────────────────────

    def test_empty_database_is_no_data_not_ready(self):
        """An empty DB must never green-light the cutover."""
        r = intent_coverage()
        self.assertTrue(r['no_data'])
        self.assertFalse(r['ready_for_cutover'])
        self.assertIsNone(r['coverage_pct'])

    def test_internal_movement_is_not_counted_as_a_gap(self):
        self._ft(with_journal=False)  # nothing crossed the boundary
        r = intent_coverage()
        self.assertEqual(r['total_rail_backed'], 0)
        self.assertTrue(r['no_data'])

    def test_surplus_distribution_never_touches_the_boundary(self):
        """An internal re-arrangement posts a journal but no settlement line, so
        it must stay out of the denominator."""
        ft, _ = create_fin_transaction(
            idempotency_key="surplus-1",
            op_type=FinancialTransaction.OpType.SURPLUS_DISTRIBUTION,
            amount=Decimal("100"), initiated_by=self.user,
            initial_state=FinancialTransaction.State.SUCCESS,
        )
        post_journal(
            idempotency_key="je-surplus-1", op_type=pm.Op.SURPLUS_DISTRIBUTION,
            lines=pm.distribute_surplus_lines(
                fund_id=1, allocations=[pm.Allocation(member=self.user,
                                                      amount=Money("100"))]),
            financial_transaction=ft, created_by=self.user,
        )
        r = intent_coverage()
        self.assertEqual(r['total_rail_backed'], 0)

    # ── the payout path (what the old report measured) ───────────────────────

    def test_rail_backed_without_intent_is_uncovered(self):
        ft = self._ft()
        r = intent_coverage()
        self.assertEqual(r['total_rail_backed'], 1)
        self.assertEqual(r['uncovered'], 1)
        self.assertEqual(r['coverage_pct'], 0.0)
        self.assertFalse(r['ready_for_cutover'])
        self.assertEqual(r['uncovered_by_op_type'],
                         {FinancialTransaction.OpType.DISBURSEMENT: 1})
        # No intent and no receipt to recover — a payout dispatched before the
        # intent became the record leaves nothing to correlate, so it is a
        # triage question rather than a backfill.
        self.assertEqual(r['review_sample'][0]['ft_id'], ft.id)
        self.assertEqual(r['review_sample'][0]['bucket'], 'unattributable')

    def test_full_coverage_is_ready(self):
        ft = self._ft()
        self._intent(ft, provider_ref="CONV_2", receipt="RCP_2")
        r = intent_coverage()
        self.assertEqual(r['covered'], 1)
        self.assertEqual(r['uncovered'], 0)
        self.assertEqual(r['coverage_pct'], 100.0)
        self.assertEqual(r['verdict'], READY)
        self.assertTrue(r['ready_for_cutover'])

    def test_an_intent_with_blank_rail_fields_still_covers(self):
        """Coverage asks whether the rail record exists, not whether it is
        complete — an intent minted before dispatch has a blank ref."""
        ft = self._ft()
        self._intent(ft, provider_ref="", receipt="")
        r = intent_coverage()
        self.assertEqual(r['covered'], 1)
        self.assertEqual(r['uncovered'], 0)

    # ── the collection blind spot ────────────────────────────────────────────

    def test_collection_with_no_rail_columns_is_still_counted(self):
        """The regression this report exists to prevent: a pay-in has nothing on
        the FT to mark it as rail-backed, and must not be mistaken for an
        internal movement."""
        self._collection_ft(idempotency_key="contrib-stk-SGH4KLM9N2")
        r = intent_coverage()
        self.assertEqual(r['total_rail_backed'], 1)
        self.assertEqual(r['covered'], 0)
        self.assertFalse(r['ready_for_cutover'])

    def test_orphan_stk_intent_makes_a_collection_linkable(self):
        """The STK intent exists but was never linked to its FT, so the backfill
        is a link job rather than a reconstruction."""
        ft = self._collection_ft(idempotency_key="contrib-stk-SGH4KLM9N2")
        intent = self._orphan_collection_intent(
            provider_ref="ws_CO_123", receipt="SGH4KLM9N2")
        r = intent_coverage()
        self.assertEqual(r['linkable'], 1)
        self.assertEqual(r['missing'], 0)
        self.assertEqual(r['verdict'], NEEDS_BACKFILL)
        row = r['uncovered_sample'][0]
        self.assertEqual(row['ft_id'], ft.id)
        self.assertEqual(row['bucket'], 'linkable')
        self.assertEqual(row['linkable_intent_id'], intent.id)

    def test_paybill_collection_with_no_intent_anywhere_is_missing(self):
        """A C2B deposit never had an initiation, so no intent exists to link —
        one has to be minted from the rail's own records."""
        self._collection_ft(idempotency_key="contrib-7-SGH4KLM9N2")
        r = intent_coverage()
        self.assertEqual(r['missing'], 1)
        self.assertEqual(r['linkable'], 0)
        self.assertEqual(r['verdict'], NEEDS_BACKFILL)
        self.assertEqual(r['uncovered_sample'][0]['receipt_hint'], "SGH4KLM9N2")

    def test_manual_contribution_is_unattributable_not_a_backfill(self):
        """An off-rail posting has no receipt to find; it is a triage question,
        never something a backfill can fix."""
        self._collection_ft(idempotency_key="contrib-7-99-manual")
        r = intent_coverage()
        self.assertEqual(r['unattributable'], 1)
        self.assertEqual(r['gap'], 0)
        self.assertEqual(r['verdict'], NEEDS_REVIEW)
        self.assertFalse(r['ready_for_cutover'])
        self.assertEqual(r['review_sample'][0]['bucket'], 'unattributable')

    def test_unattributable_alone_still_withholds_ready(self):
        """Ready means "we checked everything", so anything unexplained blocks —
        the whole failure this report was rewritten to prevent."""
        ft = self._ft()
        self._intent(ft, provider_ref="CONV_7", receipt="RCP_7")
        self._collection_ft(idempotency_key="contrib-7-99-manual")
        r = intent_coverage()
        self.assertEqual(r['covered'], 1)
        self.assertEqual(r['gap'], 0)
        self.assertEqual(r['unattributable'], 1)
        self.assertFalse(r['ready_for_cutover'])

    def test_fully_linked_collection_is_ready(self):
        """Once the backfill has run, the same database reads as ready."""
        ft = self._collection_ft(idempotency_key="contrib-stk-SGH4KLM9N2")
        PaymentIntent.objects.create(
            provider="mpesa", direction=PaymentIntent.Direction.COLLECTION,
            status=PaymentIntent.Status.SUCCEEDED, amount=Decimal("500"),
            idempotency_key="pi-collect-ws_CO_123", provider_ref="ws_CO_123",
            receipt="SGH4KLM9N2", financial_transaction=ft,
        )
        r = intent_coverage()
        self.assertEqual(r['covered'], 1)
        self.assertEqual(r['coverage_pct'], 100.0)
        self.assertEqual(r['verdict'], READY)
        self.assertTrue(r['ready_for_cutover'])


class ReceiptHintTests(TestCase):
    """The receipt only survives inside the FT's idempotency key, so reading it
    back out has to tell a real receipt from a row id or a sentinel."""

    def setUp(self):
        self.user = User.objects.create(phone_number="+254700000741")

    def _key(self, key):
        ft, _ = create_fin_transaction(
            idempotency_key=key, op_type=FinancialTransaction.OpType.CONTRIBUTION,
            amount=Decimal("1"), initiated_by=self.user)
        return receipt_hint(ft)

    def test_reads_the_receipt_from_each_collection_key_shape(self):
        self.assertEqual(self._key("contrib-stk-SGH4KLM9N2"), "SGH4KLM9N2")
        self.assertEqual(self._key("contrib-7-SGH4KLM9N3"), "SGH4KLM9N3")
        self.assertEqual(self._key("welfare-contrib-3-9-SGH4KLM9N4"), "SGH4KLM9N4")
        self.assertEqual(self._key("shares-3-9-SGH4KLM9N5"), "SGH4KLM9N5")
        self.assertEqual(self._key("advance-repay-4-SGH4KLM9N6"), "SGH4KLM9N6")

    def test_rejects_sentinels_and_row_ids(self):
        self.assertEqual(self._key("contrib-7-99-manual"), "")
        self.assertEqual(self._key("welfare-claim-42"), "")
        self.assertEqual(self._key("advance-disb-7"), "")
        self.assertEqual(self._key("welfare-contrib-3-9-None"), "")

    def test_the_idempotency_key_is_the_only_source_left(self):
        """FT used to carry a receipt column and the hint preferred it. The
        column is gone (ADR-0030), so a key with no receipt in it yields
        nothing — and the movement is classified ``unattributable`` rather than
        silently counted as ready."""
        ft, _ = create_fin_transaction(
            idempotency_key="advance-disb-7",
            op_type=FinancialTransaction.OpType.DISBURSEMENT,
            amount=Decimal("1"), initiated_by=self.user)
        self.assertEqual(receipt_hint(ft), "")
