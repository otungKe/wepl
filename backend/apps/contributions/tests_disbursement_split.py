"""A voted payout is the group's spend, split across shares (ADR-0027 §0.1).

Money in a pool belongs to the group and each member holds a share. When the
group votes a payout, every funded member's share bears its pro-rata part of the
cost — the requester is not charged the whole amount, which used to leave them
showing a debt to the others.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.communities.models import CommunityMembership
from apps.communities.services import CommunityService
from apps.contributions.services import ContributionService, DisbursementService
from apps.ledger import coa, posting_map as pm
from apps.ledger.balances import (
    account_balance, fund_balance, member_fund_balance, trial_balance,
)
from apps.ledger.models import FinancialTransaction, JournalEntry
from apps.ledger.money import Money
from apps.ledger.posting import post_journal, reverse_financial_transaction

User = get_user_model()


def _verified(phone):
    from apps.verification.models import KYCProfile
    user = User.objects.create(phone_number=phone, is_phone_verified=True)
    KYCProfile.objects.create(
        user=user, status="approved", given_names="Test", surname="User",
        id_number=f"ID{user.pk}", date_of_birth=date(1990, 1, 1),
    )
    return user


class VotedPayoutSplitTests(TestCase):
    def setUp(self):
        coa.seed_chart_of_accounts()
        self.alice = _verified("+254700000970")
        self.bob = _verified("+254700000971")
        self.carol = _verified("+254700000972")
        self.dan = _verified("+254700000973")
        community = CommunityService.create_community(self.alice, {"name": "Split Chama"})
        # The 30-day vote cooling-off is not what these tests exercise.
        type(community).objects.filter(pk=community.pk).update(cooling_off_days=0)
        community.refresh_from_db()
        for user in (self.bob, self.carol, self.dan):
            CommunityService.join_community(user, community)
        CommunityMembership.objects.filter(
            community=community, user__in=[self.bob, self.carol]).update(role="admin")
        self.c = ContributionService.create_contribution(self.alice, {
            "title": "Pool", "contribution_type": "POOL", "visibility": "closed",
            "community": community, "voting_threshold": "50",
        })
        for user in (self.bob, self.carol, self.dan):
            ContributionService.join_contribution(self.c.id, user)
        # Alice 6,000 · Bob 3,000 · Carol 1,000 · Dan nothing yet.
        self._fund(self.alice, "6000")
        self._fund(self.bob, "3000")
        self._fund(self.carol, "1000")

    def _fund(self, member, amount):
        post_journal(idempotency_key=f"fund-{member.pk}", op_type=pm.Op.CONTRIBUTION,
                     lines=pm.contribution_lines(member=member, fund_type="contribution",
                                                 fund_id=self.c.id, gross=Money(amount)))

    def _share(self, member):
        return member_fund_balance(member, "contribution", self.c.id)

    def _approve(self, requester, amount):
        req = DisbursementService.create_request(
            self.c.id, requester, Decimal(amount), "Venue", "+254700000999")
        voters = [u for u in (self.bob, self.carol, self.alice) if u != requester]
        for voter in voters:
            req.refresh_from_db()
            if req.status != "PENDING":
                break
            DisbursementService.vote(req.id, voter, "APPROVE")
        req.refresh_from_db()
        self.assertEqual(req.status, "EXECUTED")
        return req

    def test_payout_is_split_pro_rata_not_charged_to_requester(self):
        self._approve(self.alice, "1000")
        self.assertEqual(self._share(self.alice), Decimal("5400"))   # 6000 − 600
        self.assertEqual(self._share(self.bob), Decimal("2700"))     # 3000 − 300
        self.assertEqual(self._share(self.carol), Decimal("900"))    # 1000 − 100
        self.assertEqual(fund_balance("contribution", self.c.id), Decimal("9000"))
        self.assertEqual(account_balance(coa.mpesa_float_account()), Decimal("9000"))
        self.assertTrue(trial_balance()["balanced"])

    def test_requester_with_no_share_owes_the_group_nothing(self):
        self._approve(self.dan, "1000")
        self.assertEqual(self._share(self.dan), Decimal("0"))
        self.assertEqual(
            self._share(self.alice) + self._share(self.bob) + self._share(self.carol),
            Decimal("9000"))

    def test_split_sums_to_the_payout_to_the_cent(self):
        self._approve(self.alice, "100.01")
        total = sum((self._share(u) for u in (self.alice, self.bob, self.carol)), Decimal("0"))
        self.assertEqual(total, Decimal("9899.99"))
        self.assertTrue(trial_balance()["balanced"])

    def test_failed_payout_reversal_restores_every_share(self):
        req = self._approve(self.alice, "1000")
        ft = FinancialTransaction.objects.get(idempotency_key=f"disb-exec-{req.id}")
        reverse_financial_transaction(ft, note="payout failed")
        self.assertEqual(self._share(self.alice), Decimal("6000"))
        self.assertEqual(self._share(self.bob), Decimal("3000"))
        self.assertEqual(self._share(self.carol), Decimal("1000"))
        self.assertEqual(fund_balance("contribution", self.c.id), Decimal("10000"))
        self.assertTrue(trial_balance()["balanced"])

    def test_journal_keeps_the_disbursement_op_type(self):
        req = self._approve(self.alice, "1000")
        je = JournalEntry.objects.get(idempotency_key=f"je-disb-exec-{req.id}")
        self.assertEqual(je.op_type, pm.Op.DISBURSEMENT)
        self.assertEqual(je.lines.count(), 4)   # three shares + float

    # The split must not change whose payout it reads as in the history.

    def test_shared_history_names_the_requester(self):
        from apps.contributions.history import contribution_history_qs
        req = self._approve(self.dan, "1000")
        ft = FinancialTransaction.objects.get(idempotency_key=f"disb-exec-{req.id}")
        row = contribution_history_qs(self.c).get(pk=ft.pk)
        self.assertEqual(row.party_id, self.dan.id)

    def test_requester_with_no_share_still_sees_their_payout(self):
        from apps.contributions.history import member_history_qs
        req = self._approve(self.dan, "1000")
        ft = FinancialTransaction.objects.get(idempotency_key=f"disb-exec-{req.id}")
        self.assertIn(ft.pk, member_history_qs(self.dan).values_list("pk", flat=True))

    def test_received_counts_the_payout_for_the_requester_only(self):
        from apps.contributions.history import member_summary
        self._approve(self.alice, "1000")
        self.assertEqual(member_summary(self.alice)["total_received"], Decimal("1000"))
        self.assertEqual(member_summary(self.bob)["total_received"], Decimal("0"))

    def test_reversed_payout_is_not_received(self):
        from apps.contributions.history import member_summary
        req = self._approve(self.alice, "1000")
        ft = FinancialTransaction.objects.get(idempotency_key=f"disb-exec-{req.id}")
        reverse_financial_transaction(ft, note="payout failed")
        self.assertEqual(member_summary(self.alice)["total_received"], Decimal("0"))
