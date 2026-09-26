"""Communities' part in closing an account and exporting its data
(``apps.core.lifecycle``, boundary audit step 8)."""
from apps.core import lifecycle

from .models import Community, CommunityMembership


def blockers(user) -> list[str]:
    reasons = []
    for community in Community.objects.filter(created_by=user):
        others = CommunityMembership.objects.filter(
            community=community, is_active=True,
        ).exclude(user=user).count()
        if others:
            reasons.append(
                f"You are the creator of '{community.name}' which has {others} active "
                "member(s). Transfer ownership or ask all members to leave before "
                "deleting your account."
            )
    return reasons


def export(user) -> dict:
    return {"communities": [
        {"name": m.community.name, "role": m.role,
         "joined_at": m.joined_at.isoformat(), "is_active": m.is_active}
        for m in CommunityMembership.objects.filter(user=user).select_related("community")
    ]}


def register() -> None:
    lifecycle.register("communities", blockers=blockers, export=export)
