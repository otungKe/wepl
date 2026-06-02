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

    @staticmethod
    def eligible_voter_count(contribution, threshold: str, excluding_user) -> int:
        """
        Count how many people can vote on a governance action for *contribution*
        under *threshold*, excluding *excluding_user* (the actor/requester).

        threshold values:
          'admins' → contribution creator + community admins/treasurers
          '50', '67', '100', or any numeric string → all active participants
        """
        from apps.contributions.models import ContributionParticipant

        if threshold == 'admins':
            count = 0
            # Contribution creator is always an eligible admin voter
            if (contribution.created_by_id is not None and
                    contribution.created_by_id != excluding_user.id):
                count += 1
            if contribution.community_id:
                from apps.communities.models import CommunityMembership
                count += CommunityMembership.objects.filter(
                    community_id=contribution.community_id,
                    role__in=['admin', 'treasurer'],
                    is_active=True,
                ).exclude(user=excluding_user).count()
            return count
        else:
            # Percentage-based: all active participants excluding the actor
            return ContributionParticipant.objects.filter(
                contribution=contribution, is_active=True,
            ).exclude(user=excluding_user).count()

    @staticmethod
    def assert_quorum_exists(
        contribution,
        threshold: str,
        actor,
        action: str = "this action",
    ) -> None:
        """
        Raise ValidationError if no eligible voter exists for the given threshold,
        excluding the actor.

        Call this before creating any governance request (disbursement, amendment)
        so the actor discovers the deadlock immediately rather than submitting a
        request that can never be approved.

        Args:
            contribution: the Contribution being governed
            threshold:    the voting threshold string ('admins', '50', etc.)
            actor:        the user initiating the action
            action:       human-readable action name for the error message
        """
        from django.core.exceptions import ValidationError

        count = FinancialPermissions.eligible_voter_count(contribution, threshold, actor)
        if count == 0:
            if threshold == 'admins':
                detail = (
                    "The approval threshold is 'Admins only' but there are no "
                    "other admins who can vote on your request."
                )
                fix = (
                    "Ask a community admin to change the approval threshold, "
                    "or to perform this action on your behalf."
                )
            else:
                detail = (
                    f"The approval threshold requires {threshold}% of members "
                    "but there are no other active participants who can vote."
                )
                fix = "Add more members to this contribution first."

            raise ValidationError(
                f"Cannot {action}: {detail} {fix}"
            )
