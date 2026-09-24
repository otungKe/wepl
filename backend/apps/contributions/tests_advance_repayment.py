"""Advance repayment: idempotency, and the derived ``amount_repaid``.

``EmergencyAdvanceTests`` in tests.py is quarantined under P0-02 (#14), so the
repayment path has no live coverage of its own. This file is deliberately
separate and unskipped: the behaviour it pins is a money bug, not legacy shape.
"""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.communities.models import CommunityMembership
from apps.contributions.models import EmergencyAdvance
from apps.contributions.services import ContributionService, EmergencyAdvanceService
from apps.ledger import coa
from apps.ledger.balances import account_balance, advance_repaid_totals, trial_balance
from apps.ledger.models import JournalEntry
from apps.contributions.tests import make_user, make_community, approve_kyc


class AdvanceRepaymentReplayTests(TestCase):

    def setUp(self):
        coa.seed_chart_of_accounts()
        self.alice = make_user("+254700000840")
        approve_kyc(self.alice)
        self.bob = make_user("+254700000841")
        self.community = make_community(self.alice, "Advance Replay Chama")
        from apps.communities.services import CommunityService
        CommunityService.join_community(self.bob, self.community)
        CommunityMembership.objects.filter(
            community=self.community, user=self.bob).update(role="admin")
        self.c = ContributionService.create_contribution(self.alice, {
            "title": "Pool", "contribution_type": "POOL",
            "visibility": "closed", "community": self.community,
        })
        ContributionService.join_contribution(self.c.id, self.bob)
        ContributionService.contribute(self.alice, self.c.id, Decimal("10000"))
        # An advance is gated behind the community cooling-off window; backdate
        # the memberships so the request below is about repayment, not eligibility.
        CommunityMembership.objects.filter(community=self.community).update(
            joined_at=timezone.now() - timedelta(days=90))
        self.advance = EmergencyAdvanceService.request_advance(
            self.c.id, self.alice, Decimal("5000"), Decimal("10"), None)
        EmergencyAdvanceService.approve_advance(self.advance.id, self.bob)

    def test_replayed_repayment_does_not_double_count(self):
        """``amount_repaid`` is a separate write from the journal.

        repay() is driven from the settlement path, which delivers at-least-once.
        post_journal dedupes on its own key, but the counter did not: a replayed
        callback incremented it a second time, so a part-repaid advance could
        reach total_due on paper and flip to REPAID while still owing — with the
        ledger, correctly, showing only one repayment.
        """
        for _ in range(2):   # duplicate callback, same receipt
            EmergencyAdvanceService.repay(
                self.advance.id, self.alice, Decimal("3000"), mpesa_receipt="RPY_DUP")

        advance = EmergencyAdvance.objects.get(pk=self.advance.pk)
        self.assertEqual(advance.amount_repaid, Decimal("3000.00"))
        self.assertNotEqual(advance.status, "REPAID")   # 3000 of 5500 is not repaid
        self.assertEqual(
            JournalEntry.objects.filter(
                idempotency_key=f"je-advance-repay-{self.advance.id}-RPY_DUP").count(), 1)
        self.assertTrue(trial_balance()['balanced'])

    def test_distinct_repayments_accumulate(self):
        for receipt, amount in (("RPY_A", Decimal("2000")), ("RPY_B", Decimal("1500"))):
            EmergencyAdvanceService.repay(
                self.advance.id, self.alice, amount, mpesa_receipt=receipt)

        advance = EmergencyAdvance.objects.get(pk=self.advance.pk)
        self.assertEqual(advance.amount_repaid, Decimal("3500.00"))
        self.assertNotEqual(advance.status, "REPAID")

    def test_full_repayment_still_marks_repaid(self):
        EmergencyAdvanceService.repay(
            self.advance.id, self.alice, Decimal("5500"), mpesa_receipt="RPY_FULL")
        advance = EmergencyAdvance.objects.get(pk=self.advance.pk)
        self.assertEqual(advance.status, "REPAID")
        self.assertEqual(advance.balance_due, Decimal("0"))


class AmountRepaidIsDerivedTests(TestCase):
    """``amount_repaid`` carries no column: it is summed from the advance's
    repayment journals.

    The counter drifted for the reason ADR-0002 gives for not having one — a
    mutable figure written alongside, but separately from, the journal. Derived,
    a replay cannot move it at all: post_journal refuses the duplicate and there
    is no second write left to get wrong.
    """

    def setUp(self):
        coa.seed_chart_of_accounts()
        self.alice = make_user("+254700000850")
        approve_kyc(self.alice)
        self.bob = make_user("+254700000851")
        approve_kyc(self.bob)
        self.community = make_community(self.alice, "Derived Advance Chama")
        from apps.communities.services import CommunityService
        CommunityService.join_community(self.bob, self.community)
        CommunityMembership.objects.filter(
            community=self.community, user=self.bob).update(role="admin")
        self.c = ContributionService.create_contribution(self.alice, {
            "title": "Pool", "contribution_type": "POOL",
            "visibility": "closed", "community": self.community,
        })
        ContributionService.join_contribution(self.c.id, self.bob)
        ContributionService.contribute(self.alice, self.c.id, Decimal("10000"))
        ContributionService.contribute(self.bob, self.c.id, Decimal("5000"))
        CommunityMembership.objects.filter(community=self.community).update(
            joined_at=timezone.now() - timedelta(days=90))
        self.advance = EmergencyAdvanceService.request_advance(
            self.c.id, self.alice, Decimal("5000"), Decimal("10"), None)
        EmergencyAdvanceService.approve_advance(self.advance.id, self.bob)

    def _fresh(self):
        return EmergencyAdvance.objects.get(pk=self.advance.pk)

    def test_the_model_has_no_repayment_column(self):
        """A guard against the counter coming back: if it is reintroduced as a
        field, this fails and the reviewer has to argue for it."""
        columns = {f.name for f in EmergencyAdvance._meta.get_fields()
                   if getattr(f, 'column', None)}
        self.assertNotIn('amount_repaid', columns)

    def test_an_advance_with_no_repayments_reads_zero(self):
        advance = self._fresh()
        self.assertEqual(advance.amount_repaid, Decimal("0"))
        self.assertEqual(advance.balance_due, Decimal("5500.00"))

    def test_the_figure_comes_from_the_journals_not_a_write(self):
        """Nothing writes the advance row on repayment now — the numbers come
        from the posting. This is also why a column that had over-counted a
        replay corrects itself: the journals were never wrong."""
        EmergencyAdvanceService.repay(
            self.advance.id, self.alice, Decimal("2000"), mpesa_receipt="DRV1")
        EmergencyAdvanceService.repay(
            self.advance.id, self.alice, Decimal("1000"), mpesa_receipt="DRV2")

        advance = self._fresh()
        self.assertEqual(advance.amount_repaid, Decimal("3000.00"))
        self.assertEqual(advance.balance_due, Decimal("2500.00"))

    def test_interest_beyond_the_principal_still_counts_as_repaid(self):
        """The last part of a repayment is interest, which credits a shared
        income account rather than this advance's receivable. Summing the
        receivable alone would lose it, so the cash leg is what is summed."""
        EmergencyAdvanceService.repay(
            self.advance.id, self.alice, Decimal("5000"), mpesa_receipt="INT1")
        ar = coa.member_receivable_account(user=self.alice, fund_id=self.advance.id)
        self.assertEqual(account_balance(ar), Decimal("0"))    # principal cleared

        EmergencyAdvanceService.repay(          # pure interest: no receivable line
            self.advance.id, self.alice, Decimal("500"), mpesa_receipt="INT2")

        advance = self._fresh()
        self.assertEqual(advance.amount_repaid, Decimal("5500.00"))
        self.assertEqual(advance.status, "REPAID")

    def test_one_advances_repayments_do_not_leak_into_another(self):
        other = EmergencyAdvanceService.request_advance(
            self.c.id, self.bob, Decimal("1000"), Decimal("10"), None)
        EmergencyAdvanceService.approve_advance(other.id, self.alice)
        EmergencyAdvanceService.repay(
            self.advance.id, self.alice, Decimal("2000"), mpesa_receipt="SEP1")

        self.assertEqual(self._fresh().amount_repaid, Decimal("2000.00"))
        self.assertEqual(
            EmergencyAdvance.objects.get(pk=other.pk).amount_repaid, Decimal("0"))

    def test_bulk_read_agrees_with_the_per_advance_read(self):
        EmergencyAdvanceService.repay(
            self.advance.id, self.alice, Decimal("2500"), mpesa_receipt="BLK1")
        totals = advance_repaid_totals([self.advance.id])
        self.assertEqual(totals[self.advance.id], self._fresh().amount_repaid)


class AdvanceInterestToPoolTests(AdvanceRepaymentReplayTests):
    """ADR-0027 §0.3: an advance is the group lending its own money, so the
    interest it earns is the pool's retained surplus, not Wepl's income."""

    def test_interest_credits_the_pool_surplus_not_platform_income(self):
        EmergencyAdvanceService.repay(
            self.advance.id, self.alice, Decimal("5500"), mpesa_receipt="RPY_INT")
        self.assertEqual(
            account_balance(coa.retained_surplus_account(fund_id=self.c.id)), Decimal("500"))
        self.assertEqual(account_balance(coa.interest_income_account()), Decimal("0"))
        self.assertTrue(trial_balance()['balanced'])
