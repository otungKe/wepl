"""Community authorization policy (ADR-0009).

Declares, as data, what each community role may do. Replaces the inline
``created_by_id ==`` / ``_is_admin()`` / ``role == ADMIN`` checks that were
previously scattered across ``communities/views.py`` and ``services.py``.

Model
-----
Every actor has exactly one effective *rank* relative to a community:

    creator (4) > admin (3) > treasurer (2) > member (1) > outsider (0)

The creator is always also an admin member (granted on create), but is ranked
above admins so creator-only actions (delete, ownership-level member management)
remain exclusive even to other admins.

Each action declares the *minimum rank* required. Authorization is then a single
comparison — no per-call-site role logic.

Visibility-style rules (e.g. who may see the full member list) layer the
community's own settings on top of the rank check; those live in the view/
serializer because they depend on per-instance configuration, but they call
``can(...)`` for the role part so the role logic still lives here.
"""
from apps.core.policy import policy

from .models import CommunityMembership

Role = CommunityMembership.Role

# Effective authority ranking. 'creator' is a pseudo-role above ADMIN.
CREATOR = "creator"
_RANK = {
    Role.MEMBER: 1,
    Role.TREASURER: 2,
    Role.ADMIN: 3,
    CREATOR: 4,
}

# Minimum rank required for each action. This table is the single source of
# truth for "what can each role do" in a community.
_MIN_RANK = {
    "community.view":                 _RANK[Role.MEMBER],      # any active member
    "community.members.view_all":     _RANK[Role.ADMIN],       # full roster (see note below)
    "community.update":               _RANK[Role.ADMIN],       # edit settings/governance
    "community.join_request.review":  _RANK[Role.ADMIN],       # approve/reject join requests
    # Financial administration — admins *and* treasurers. Mirrors the long-standing
    # FinancialPermissions.is_community_admin definition (creator/admin/treasurer);
    # used by contributions/welfare to gate fund management & privileged creation.
    "community.finance.manage":       _RANK[Role.TREASURER],
    "community.member.assign_role":   _RANK[CREATOR],          # change a member's role
    "community.member.remove":        _RANK[CREATOR],          # remove a member
    "community.delete":               _RANK[CREATOR],          # delete the community
    "community.archive":              _RANK[CREATOR],          # archive / un-archive
    "community.ownership.transfer":   _RANK[CREATOR],          # (reserved for ADR-0011)
}


def community_role(actor, community) -> str | None:
    """The actor's effective role: ``CREATOR``, a ``Role`` value, or ``None``."""
    if not actor or not getattr(actor, "is_authenticated", False):
        return None
    if community.created_by_id == actor.id:
        return CREATOR
    membership = community.membership_for(actor)
    return membership.role if membership else None


def community_rank(actor, community) -> int:
    """Numeric authority of *actor* over *community* (0 = outsider)."""
    role = community_role(actor, community)
    return _RANK.get(role, 0)


@policy("community")
def _resolve(actor, action: str, community) -> bool:
    try:
        needed = _MIN_RANK[action]
    except KeyError:  # unknown action — treat as a config bug, fail closed
        raise KeyError(f"Unknown community action '{action}'. Add it to _MIN_RANK.")
    return community_rank(actor, community) >= needed
