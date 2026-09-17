"""Contract tests for the settlement seam (apps.contributions.settlement) — the
provider-agnostic domain reaction to a settled payout, relocated out of the mpesa
rail app and the ledger (Move 1). The per-context routing is exercised end-to-end
by the mpesa B2C callback and ops-recovery suites; these lock the public entry
points and the context-free no-op paths."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ledger.models import FinancialTransaction as FT
from apps.contributions import settlement


class SettlementSeamTests(TestCase):
    def _ft(self, **kw):
        return FT.objects.create(
            op_type=FT.OpType.DISBURSEMENT, state=FT.State.PROCESSING,
            amount=Decimal("100.00"),
            initiated_by=get_user_model().objects.create(phone_number="254700000601"),
            idempotency_key=kw.pop("idempotency_key", "settle-1"), **kw)

    def test_no_context_is_a_noop(self):
        # An FT with no linked domain object (e.g. a manual adjustment) must not
        # raise on either path.
        ft = self._ft(context_type="", context_id=None)
        settlement.on_payout_settled(ft, "RCPT")   # no raise
        settlement.on_payout_failed(ft)            # no raise

    def test_standing_order_success_is_logging_only(self):
        ft = self._ft(context_type="standing_order", context_id=42,
                      idempotency_key="settle-so")
        settlement.on_payout_settled(ft, "RCPT")   # logs, no domain object, no raise

    def test_missing_domain_object_is_swallowed(self):
        # A context pointing at a non-existent row is tolerated (idempotent /
        # already-cleaned-up), never raised.
        ft = self._ft(context_type="welfare_claim", context_id=999999,
                      idempotency_key="settle-missing")
        settlement.on_payout_settled(ft, "RCPT")
        settlement.on_payout_failed(ft)


class CollectionSettlementTests(TestCase):
    """The relocated collection routing (Move 2): on_collection_settled drives the
    right business service off provider-agnostic primitives — proven end-to-end for
    the shares path, which had its money-posting relocated from the rail app into
    SharesService."""

    def setUp(self):
        from apps.ledger import coa
        coa.seed_chart_of_accounts()

    def test_shares_collection_credits_holding_and_posts_journal(self):
        from apps.contributions.models import SharesFund, ShareHolding
        from apps.ledger.models import FinancialTransaction
        user = get_user_model().objects.create(phone_number="254700000701")
        fund = SharesFund.objects.create(name="Test Shares", share_price=Decimal("100.00"))

        settlement.on_collection_settled(
            payment_type="shares", user=user, amount=Decimal("200.00"),
            receipt="SHRC1", shares_fund_id=fund.id, idempotency_seed="chk-1")

        holding = ShareHolding.objects.get(shares_fund=fund, user=user)
        self.assertEqual(holding.shares_count, Decimal("2.0000"))     # 200 / 100
        self.assertEqual(holding.total_contributed, Decimal("200.00"))
        self.assertTrue(FinancialTransaction.objects.filter(
            op_type=FinancialTransaction.OpType.SHARES_PURCHASE, shares_fund=fund).exists())

    def test_shares_purchase_is_idempotent_on_receipt(self):
        from apps.contributions.models import SharesFund, ShareHolding
        user = get_user_model().objects.create(phone_number="254700000702")
        fund = SharesFund.objects.create(name="Test Shares 2", share_price=Decimal("100.00"))
        for _ in range(2):   # duplicate callback → same receipt → credited once
            settlement.on_collection_settled(
                payment_type="shares", user=user, amount=Decimal("100.00"),
                receipt="DUPR", shares_fund_id=fund.id, idempotency_seed="chk-2")
        self.assertEqual(
            ShareHolding.objects.get(shares_fund=fund, user=user).shares_count,
            Decimal("1.0000"))


class C2BPaybillResolveTests(TestCase):
    """ContributionService.credit_paybill_payin — the business half of the old
    mpesa reconcile_c2b (Move 2b). Covers the resolution branches and the
    security-critical community-membership gate that had no active test before."""

    def _svc(self):
        from apps.contributions.services import ContributionService
        return ContributionService

    def test_unknown_reference(self):
        r = self._svc().credit_paybill_payin(
            reference="RANDOM-REF", phone="254700000001", amount=Decimal("100"))
        self.assertFalse(r["reconciled"])
        self.assertEqual(r["reason"], "unknown_ref")

    def test_contribution_not_found(self):
        r = self._svc().credit_paybill_payin(
            reference="WEPL-999999", phone="254700000001", amount=Decimal("100"))
        self.assertEqual(r["reason"], "contribution_not_found")

    def test_user_not_found(self):
        from apps.contributions.tests import make_user, make_contribution
        owner = make_user("254712345678")
        contrib = make_contribution(owner)   # open, no community
        r = self._svc().credit_paybill_payin(
            reference=f"WEPL-{contrib.id}", phone="254799999999", amount=Decimal("100"))
        self.assertEqual(r["reason"], "user_not_found")

    def test_membership_gate_blocks_non_member_but_records_for_review(self):
        from apps.contributions.tests import make_user, make_community, make_contribution
        owner = make_user("254712345678")
        community = make_community(owner, "Gated Chama")
        contrib = make_contribution(owner, community=community)   # community-scoped
        stranger = make_user("254701010101")   # NOT a community member
        r = self._svc().credit_paybill_payin(
            reference=f"WEPL-{contrib.id}", phone=stranger.phone_number, amount=Decimal("100"))
        self.assertFalse(r["reconciled"])
        self.assertEqual(r["reason"], "not_community_member")
        # Resolved to member+fund so the rail can record it for admin review.
        self.assertEqual(r["contribution_id"], contrib.id)
        self.assertEqual(r["user_id"], stranger.id)

    def test_open_contribution_credits_and_reconciles(self):
        from apps.ledger import coa
        from apps.ledger.models import FinancialTransaction
        from apps.contributions.tests import make_user, make_contribution, approve_kyc
        coa.seed_chart_of_accounts()
        owner = make_user("254712345678")
        approve_kyc(owner)                       # contribute() requires Tier-1
        contrib = make_contribution(owner)       # open, no community
        r = self._svc().credit_paybill_payin(
            reference=f"WEPL-{contrib.id}", phone=owner.phone_number,
            amount=Decimal("500"), receipt="C2BR1", payer_name="JANE DOE")
        self.assertTrue(r["reconciled"])
        self.assertEqual(r["reason"], "ok")
        self.assertTrue(FinancialTransaction.objects.filter(
            contribution=contrib, initiated_by=owner,
            op_type=FinancialTransaction.OpType.CONTRIBUTION).exists())
