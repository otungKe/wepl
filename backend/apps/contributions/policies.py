"""Contribution authorization policy (ADR-0009).

Brings contributions onto the centralized ``apps.core.policy`` front door. The
*implementation* of the role/membership checks already lives in the long-standing
``apps.ledger.permissions.FinancialPermissions`` helper (creator / community
admin-treasurer / active participant); this module simply registers it as the
``contribution`` resolver so call sites use the same ``can()`` / ``require()`` API
as every other resource — instead of hand-rolling ``CommunityMembership.objects
.filter(...)`` queries inline in views.

Actions
-------
``contribution.view``        member view: creator OR active participant.
``contribution.participate`` active participant only (excludes a non-joining creator).
``contribution.admin``       creator OR community admin/treasurer (governance, edits, queues).
``contribution.lifecycle``   creator only (close / reopen / archive / delete / rotation).

Community-level financial administration is expressed by the ``community`` policy's
``community.finance.manage`` capability (admins + treasurers).
"""
from apps.core.policy import policy
from apps.ledger.permissions import FinancialPermissions


def is_contribution_member(contribution, user) -> bool:
    """Creator or active participant — the 'can see this contribution' predicate."""
    if contribution.created_by_id == user.id:
        return True
    return FinancialPermissions.is_active_participant(contribution, user)


@policy("contribution")
def _resolve(actor, action: str, contribution) -> bool:
    if action == "contribution.view":
        return is_contribution_member(contribution, actor)
    if action == "contribution.participate":
        return FinancialPermissions.is_active_participant(contribution, actor)
    if action == "contribution.admin":
        return FinancialPermissions.is_contribution_admin(contribution, actor)
    if action == "contribution.lifecycle":
        return contribution.created_by_id == actor.id
    raise KeyError(f"Unknown contribution action '{action}'.")
