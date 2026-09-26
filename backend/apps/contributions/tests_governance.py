"""Group governance: one set of voting rules for payouts, amendments and pool
spends (boundary audit step 9)."""
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from . import governance
from .models import ContributionAmendment, ContributionParticipant
from .services import ContributionService
from .services.amendments import AmendmentService
from .tests import approve_kyc

User = get_user_model()


def _member(phone):
    u = User.objects.create(phone_number=phone)
    approve_kyc(u)
    return u


class RequiredApprovalsTests(TestCase):

    def setUp(self):
        self.owner = _member("+254700000701")
        self.c = ContributionService.create_contribution(self.owner, {"title": "Pool"})
        for i in range(3):  # 4 active members with the owner
            ContributionParticipant.objects.create(
                contribution=self.c, user=_member(f"+25470000071{i}"), is_active=True)

    def test_thresholds(self):
        self.assertEqual(governance.required_approvals(self.c, 'admins'), 1)
        self.assertEqual(governance.required_approvals(self.c, '25'), 1)
        self.assertEqual(governance.required_approvals(self.c, '50'), 2)
        self.assertEqual(governance.required_approvals(self.c, '67'), 3)
        self.assertEqual(governance.required_approvals(self.c, '100'), 4)
        self.assertEqual(governance.required_approvals(self.c, 'nonsense'), 1)

    def test_contribution_method_reads_the_payout_threshold(self):
        self.c.voting_threshold = '50'
        self.assertEqual(self.c.required_approvals(), 2)


class TallyTests(TestCase):

    def test_outcomes(self):
        self.assertEqual(governance.Tally(2, 0, 2).outcome, governance.PASSED)
        self.assertEqual(governance.Tally(0, 2, 2).outcome, governance.FAILED)
        self.assertIsNone(governance.Tally(1, 1, 2).outcome)


class AmendmentVoteTests(TestCase):
    """AmendmentService.vote had no tests; it now shares the tally."""

    def setUp(self):
        self.owner = _member("+254700000801")
        self.c = ContributionService.create_contribution(
            self.owner, {"title": "Pool", "voting_threshold": "admins",
                         "amendment_voting_threshold": "67"})
        self.members = [_member(f"+25470000081{i}") for i in range(3)]
        for m in self.members:
            ContributionParticipant.objects.create(contribution=self.c, user=m, is_active=True)

    def _propose(self):
        return AmendmentService.propose(self.c.id, self.owner, {"target_amount": "5000"})

    def test_percentage_amendment_uses_the_amendment_threshold(self):
        # 4 members at 67% need 3 approvals. The old code read the payout
        # threshold ('admins' = 1) here and applied the change on the first vote.
        a = self._propose()
        AmendmentService.vote(a.id, self.members[0], 'APPROVE')
        self.assertEqual(ContributionAmendment.objects.get(id=a.id).status, 'PENDING')
        AmendmentService.vote(a.id, self.members[1], 'APPROVE')
        AmendmentService.vote(a.id, self.members[2], 'APPROVE')
        self.assertEqual(ContributionAmendment.objects.get(id=a.id).status, 'APPROVED')
        self.c.refresh_from_db()
        self.assertEqual(str(self.c.target_amount), '5000.00')

    def test_rejections_reaching_the_bar_reject(self):
        a = self._propose()
        for m in self.members:
            AmendmentService.vote(a.id, m, 'REJECT')
        self.assertEqual(ContributionAmendment.objects.get(id=a.id).status, 'REJECTED')

    def test_a_member_votes_once(self):
        a = self._propose()
        AmendmentService.vote(a.id, self.members[0], 'APPROVE')
        with self.assertRaises(ValidationError):
            AmendmentService.vote(a.id, self.members[0], 'REJECT')
