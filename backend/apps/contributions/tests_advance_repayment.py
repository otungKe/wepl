"""Advance repayment idempotency.

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
from apps.ledger.balances import trial_balance
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
