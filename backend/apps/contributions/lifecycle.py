"""Group finance's part in closing an account and exporting its data
(``apps.core.lifecycle``, boundary audit step 8).

An account cannot close while the customer owes a group money or holds a share
of one: under ADR-0027 a share is paid out only by a group decision (an exit
request), so closing first would leave it stranded. Contribution and ledger
records are financial records and are kept.
"""
from apps.core import lifecycle
from apps.ledger.balances import holds_any_balance

from .history import member_history_qs, transaction_type_for
from .models import ContributionParticipant, EmergencyAdvance

OPEN_ADVANCE_STATUSES = ('PENDING', 'APPROVED', 'DISBURSED')


def blockers(user) -> list[str]:
    reasons = []
    if EmergencyAdvance.objects.filter(borrower=user, status__in=OPEN_ADVANCE_STATUSES).exists():
        reasons.append("You have outstanding advance(s) that must be repaid before "
                       "your account can be deleted.")
    if holds_any_balance(user):
        reasons.append("You still hold money in a group. Ask to leave the group and "
                       "be paid your share before deleting your account.")
    return reasons


def export(user) -> dict:
    return {
        "contributions": [
            {"title": pt.contribution.title, "type": pt.contribution.contribution_type,
             "is_active": pt.is_active}
            for pt in ContributionParticipant.objects.filter(user=user).select_related("contribution")
        ],
        # The user's own money history, ledger-derived (ADR-0002/0027).
        "transactions": [
            {"contribution": t.contribution.title, "amount": str(t.amount),
             "type": transaction_type_for(t.op_type), "platform_ref": t.reference,
             "date": t.created_at.isoformat()}
            for t in member_history_qs(user)[:500]
        ],
    }


def register() -> None:
    lifecycle.register("contributions", blockers=blockers, export=export)
