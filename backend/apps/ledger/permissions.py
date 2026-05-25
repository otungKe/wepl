"""
Central authorisation helper for all financial operations.

Replaces the six divergent _is_admin() copies scattered across services.py —
every one had slightly different role checks (e.g. 'admin' only vs 'admin,treasurer').
Now there is exactly one implementation used everywhere.

Raises django.core.exceptions.PermissionDenied (not Python's PermissionError) so
DRF's exception handler turns it into a proper 403 response automatically.
"""
from django.core.exceptions import PermissionDenied


class FinancialPermissions:

    # ── Role checks ───────────────────────────────────────────────────────────

    @staticmethod
    def is_community_admin(community, user) -> bool:
        """
        True if user is the community creator OR holds admin/treasurer membership.
        """
        if community.created_by_id == user.id:
            return True
        from apps.communities.models import CommunityMembership
        return CommunityMembership.objects.filter(
            community=community,
            user=user,
            role__in=['admin', 'treasurer'],
            is_active=True,
        ).exists()

    @staticmethod
    def is_contribution_admin(contribution, user) -> bool:
        """
        True if user can act as admin on this contribution:
          - contribution creator, OR
          - admin/treasurer in the contribution's community (if it has one)
        """
        if contribution.created_by_id == user.id:
            return True
        if contribution.community_id:
            from apps.communities.models import Community
            community = contribution.community
            return FinancialPermissions.is_community_admin(community, user)
        return False

    @staticmethod
    def is_active_participant(contribution, user) -> bool:
        from apps.contributions.models import ContributionParticipant
        return ContributionParticipant.objects.filter(
            contribution=contribution, user=user, is_active=True,
        ).exists()

    # ── Assertion helpers (raise on failure) ─────────────────────────────────

    @staticmethod
    def assert_admin(contribution, user, msg: str | None = None) -> None:
        if not FinancialPermissions.is_contribution_admin(contribution, user):
            raise PermissionDenied(msg or "Only contribution admins can perform this action.")

    @staticmethod
    def assert_participant(contribution, user, msg: str | None = None) -> None:
        if not FinancialPermissions.is_active_participant(contribution, user):
            raise PermissionDenied(msg or "You must be an active participant in this contribution.")

    @staticmethod
    def assert_community_admin(community, user, msg: str | None = None) -> None:
        if not FinancialPermissions.is_community_admin(community, user):
            raise PermissionDenied(msg or "Only community admins can perform this action.")
