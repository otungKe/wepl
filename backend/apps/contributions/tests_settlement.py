"""Contract tests for the settlement seam (apps.contributions.settlement) — the
provider-agnostic domain reaction to a settled payout, relocated out of the mpesa
rail app and the ledger (Move 1). The per-context routing is exercised end-to-end
by the mpesa B2C callback and ops-recovery suites; these lock the public entry
points and the context-free no-op paths."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Prefetch
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
        holding = ShareHolding.objects.get(shares_fund=fund, user=user)
        self.assertEqual(holding.shares_count, Decimal("1.0000"))
        self.assertEqual(holding.total_contributed, Decimal("100.00"))

    def test_repeat_share_purchases_accumulate(self):
        """Distinct receipts are distinct purchases and must ADD to the holding.

        Asserting a single-purchase value after replaying ONE receipt (the test
        above) cannot tell "credited once" apart from "reset then credited once":
        `update_or_create(..., defaults={'shares_count': 0, ...})` applied its
        defaults to the existing row, so a member's holding only ever showed
        their latest purchase. Only an accumulation across ≥2 distinct keys
        distinguishes the two.
        """
        from apps.contributions.models import SharesFund, ShareHolding
        user = get_user_model().objects.create(phone_number="254700000703")
        fund = SharesFund.objects.create(name="Test Shares 3", share_price=Decimal("100.00"))
        for receipt in ("SHRA1", "SHRA2", "SHRA3"):
            settlement.on_collection_settled(
                payment_type="shares", user=user, amount=Decimal("500.00"),
                receipt=receipt, shares_fund_id=fund.id, idempotency_seed=receipt)

        holding = ShareHolding.objects.get(shares_fund=fund, user=user)
        self.assertEqual(holding.shares_count, Decimal("15.0000"))       # 3 × 500/100
        self.assertEqual(holding.total_contributed, Decimal("1500.00"))

    def test_replay_after_several_purchases_changes_nothing(self):
        """A duplicate delivery must not move the holding. The journal dedupes on
        its own key and the holding now reads off that journal, so this asserts
        the guarantee end to end rather than the counter write it used to."""
        from apps.contributions.models import SharesFund, ShareHolding
        user = get_user_model().objects.create(phone_number="254700000704")
        fund = SharesFund.objects.create(name="Test Shares 4", share_price=Decimal("100.00"))
        for receipt in ("SHRB1", "SHRB2"):
            settlement.on_collection_settled(
                payment_type="shares", user=user, amount=Decimal("300.00"),
                receipt=receipt, shares_fund_id=fund.id, idempotency_seed=receipt)

        before = ShareHolding.objects.get(shares_fund=fund, user=user)
        self.assertEqual(before.shares_count, Decimal("6.0000"))

        settlement.on_collection_settled(   # duplicate delivery of the first one
            payment_type="shares", user=user, amount=Decimal("300.00"),
            receipt="SHRB1", shares_fund_id=fund.id, idempotency_seed="SHRB1")

        after = ShareHolding.objects.get(shares_fund=fund, user=user)
        self.assertEqual(after.shares_count, Decimal("6.0000"))
        self.assertEqual(after.total_contributed, Decimal("600.00"))


class ShareHoldingIsDerivedTests(TestCase):
    """ShareHolding carries no money columns: ``shares_count`` and
    ``total_contributed`` are read from the member's shares sub-ledger.

    The counters drifted for the reason ADR-0002 gives for not having them — a
    mutable balance written alongside, but separately from, the journal. The CI
    grep-guard never saw them, because it names the specific symbols ADR-0002
    removed rather than the rule."""

    def setUp(self):
        from apps.ledger import coa
        coa.seed_chart_of_accounts()
        self.user = get_user_model().objects.create(phone_number="254700000710")

    def _fund(self, name="Derived Shares", price="100.00"):
        from apps.contributions.models import SharesFund
        return SharesFund.objects.create(name=name, share_price=Decimal(price))

    def _buy(self, fund, user, amount, receipt):
        settlement.on_collection_settled(
            payment_type="shares", user=user, amount=Decimal(amount),
            receipt=receipt, shares_fund_id=fund.id, idempotency_seed=receipt)

    def test_the_model_has_no_money_columns(self):
        """A guard against the counters coming back: if either is reintroduced as
        a field, this fails and the reviewer has to argue for it."""
        from apps.contributions.models import ShareHolding
        columns = {f.name for f in ShareHolding._meta.get_fields() if getattr(f, 'column', None)}
        self.assertNotIn('shares_count', columns)
        self.assertNotIn('total_contributed', columns)

    def test_a_row_created_before_any_purchase_reads_zero(self):
        """Community creation enrols the owner with an empty holding row. It must
        read zero rather than a default that later drifts."""
        from apps.contributions.models import ShareHolding
        fund = self._fund("Empty Shares")
        holding = ShareHolding.objects.create(shares_fund=fund, user=self.user)
        self.assertEqual(holding.shares_count, Decimal("0"))
        self.assertEqual(holding.total_contributed, Decimal("0"))
        self.assertEqual(holding.ownership_pct, Decimal("0"))

    def test_an_enrolled_row_picks_up_purchases_without_being_written_to(self):
        """The row that already existed is never updated by the purchase — the
        numbers come from the posting. This is also why holdings understated by
        the old reset bug correct themselves: the ledger was never wrong."""
        from apps.contributions.models import ShareHolding
        fund = self._fund("Enrolled Shares")
        ShareHolding.objects.create(shares_fund=fund, user=self.user)
        self._buy(fund, self.user, "500.00", "DRV1")
        self._buy(fund, self.user, "250.00", "DRV2")

        holding = ShareHolding.objects.get(shares_fund=fund, user=self.user)
        self.assertEqual(holding.total_contributed, Decimal("750.00"))
        self.assertEqual(holding.shares_count, Decimal("7.5000"))

    def test_ownership_splits_on_the_same_basis_as_the_pool(self):
        """Numerator and denominator now come from the same ledger read, so the
        holders' percentages account for the whole pool."""
        from apps.contributions.models import ShareHolding
        other = get_user_model().objects.create(phone_number="254700000711")
        fund = self._fund("Split Shares")
        self._buy(fund, self.user, "750.00", "SPL1")
        self._buy(fund, other, "250.00", "SPL2")

        pcts = [ShareHolding.objects.get(shares_fund=fund, user=u).ownership_pct
                for u in (self.user, other)]
        self.assertEqual(pcts, [Decimal("75.00"), Decimal("25.00")])
        self.assertEqual(sum(pcts), Decimal("100.00"))

    def test_serializing_a_fund_does_not_scale_its_queries_with_its_holders(self):
        """The figures are ledger reads, so a naive walk costs a balance query
        and a pool query per holder. Both are answerable in bulk, and the count
        must not move when a holder is added."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        from apps.contributions.models import ShareHolding, SharesFund
        from apps.contributions.serializers import SharesFundSerializer

        def serialize(fund):
            fresh = SharesFund.objects.prefetch_related(
                Prefetch('holdings', queryset=ShareHolding.objects.select_related('user')),
            ).get(pk=fund.pk)
            with CaptureQueriesContext(connection) as ctx:
                data = SharesFundSerializer(fresh).data
                self.assertEqual(len(data["holdings"]), fresh.holdings.count())
            return len(ctx)

        fund = self._fund("Query Count Shares")
        self._buy(fund, self.user, "100.00", "QC1")
        with_one = serialize(fund)

        for i in range(4):
            member = get_user_model().objects.create(phone_number=f"25470000072{i}")
            self._buy(fund, member, "100.00", f"QC2{i}")
        with_five = serialize(fund)

        self.assertEqual(
            with_one, with_five,
            f"query count grew with holders: {with_one} -> {with_five}")

    def test_the_fund_total_is_the_pool_over_the_share_price(self):
        from apps.contributions.serializers import SharesFundSerializer
        fund = self._fund("Total Shares", price="50.00")
        self._buy(fund, self.user, "500.00", "TOT1")
        data = SharesFundSerializer(fund).data
        self.assertEqual(Decimal(data["total_shares"]), Decimal("10.0000"))
        self.assertEqual(Decimal(data["total_pool"]), Decimal("500.00"))


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
