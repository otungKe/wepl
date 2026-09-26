"""Group governance: how a group decides (boundary audit step 9).

A payout request, a change to the group's rules and a spend or distribution
from the pool are all proposals the group votes on. Each keeps its own proposal
and vote table (moving live rows is a later step), but the rules they vote by
live here once:

``required_approvals(contribution, threshold)``
    How many approvals a threshold demands from the group as it is now.
``record_vote(votes, voter, choice)``
    One vote per member per proposal.
``tally(votes, required)``
    Whether the proposal has now passed, failed or is still open.

Welfare claims are decided by one admin or treasurer, not by a vote, and do not
use this.
"""
import math
from dataclasses import dataclass

from django.core.exceptions import ValidationError

APPROVE = 'APPROVE'
REJECT = 'REJECT'

PASSED = 'passed'
FAILED = 'failed'


def required_approvals(contribution, threshold: str) -> int:
    """Approvals ``threshold`` needs from ``contribution``'s active members.

    'admins' needs one admin; '100' needs everyone; a percentage string
    ('25', '50', '67', ...) needs that share, rounded up. At least one;
    unknown values need one."""
    total = contribution.participants.filter(is_active=True).count()
    if threshold == 'admins':
        return 1
    try:
        pct = int(threshold)
    except (ValueError, TypeError):
        return 1
    if pct <= 0:
        return 1
    if pct >= 100:
        return max(1, total)
    return max(1, math.ceil(total * pct / 100))


def record_vote(votes, voter, choice: str = APPROVE, *, already: str):
    """Record ``voter``'s vote through ``votes`` (the proposal's related vote
    manager). Raises ``ValidationError(already)`` on a second vote."""
    defaults = {'vote': choice} if hasattr(votes.model, 'vote') else {}
    field = 'approver' if hasattr(votes.model, 'approver') else 'voter'
    _, created = votes.get_or_create(**{field: voter}, defaults=defaults)
    if not created:
        raise ValidationError(already)


@dataclass(frozen=True)
class Tally:
    approvals: int
    rejections: int
    required: int

    @property
    def outcome(self):
        """PASSED once approvals reach the bar, FAILED once rejections do,
        otherwise None (still open). Approval is checked first."""
        if self.approvals >= self.required:
            return PASSED
        if self.rejections >= self.required:
            return FAILED
        return None


def tally(votes, required: int) -> Tally:
    """Count ``votes`` against ``required``. A table without a ``vote`` column
    stores approvals only."""
    if hasattr(votes.model, 'vote'):
        return Tally(votes.filter(vote=APPROVE).count(),
                     votes.filter(vote=REJECT).count(), required)
    return Tally(votes.count(), 0, required)
