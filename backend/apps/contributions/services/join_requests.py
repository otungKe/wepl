from ._common import *  # shared imports + helpers (ADR-0013)
from .contribution import ContributionService


class ContributionJoinRequestService:

    @staticmethod
    def _is_community_member(contribution, user):
        if not contribution.community:
            return True
        from apps.communities.models import CommunityMembership
        return CommunityMembership.objects.filter(
            community=contribution.community, user=user, is_active=True,
        ).exists()

    @staticmethod
    def _already_participant(contribution, user):
        return ContributionParticipant.objects.filter(
            contribution=contribution, user=user, is_active=True,
        ).exists()

    @staticmethod
    def request_join(contribution_id, user):
        from apps.communities.models import CommunityMembership

        contribution = Contribution.objects.select_related('community', 'created_by').get(
            id=contribution_id
        )

        if contribution.status != 'active':
            raise ValidationError("This contribution is not accepting new members.")

        if not ContributionJoinRequestService._is_community_member(contribution, user):
            raise PermissionDenied(
                "You must be a member of this community to request joining this contribution."
            )

        if ContributionJoinRequestService._already_participant(contribution, user):
            raise ValidationError("You are already a participant in this contribution.")

        existing = ContributionJoinRequest.objects.filter(
            contribution=contribution, user=user
        ).first()
        if existing:
            if existing.status == 'PENDING':
                raise ValidationError(
                    "You already have a pending request for this contribution."
                )
            if existing.status == 'APPROVED':
                raise ValidationError("Your request was already approved.")
            existing.status       = 'PENDING'
            existing.request_type = 'REQUEST'
            existing.invited_by   = None
            existing.reviewed_at  = None
            existing.reviewed_by  = None
            existing.save()
            jr = existing
        else:
            jr = ContributionJoinRequest.objects.create(
                contribution=contribution,
                user=user,
                request_type='REQUEST',
            )

        display = user.name or user.phone_number
        admins_notified = {contribution.created_by.id}
        _notify(
            user=contribution.created_by,
            notification_type='contribution_join_request',
            title=f"Join request — {contribution.title}",
            message=f"{display} wants to join {contribution.title}. Tap to review.",
            contribution_id=contribution.id,
            join_request_id=jr.id,
        )

        if contribution.community:
            for m in CommunityMembership.objects.filter(
                community=contribution.community,
                role__in=['admin', 'treasurer'],
                is_active=True,
            ).exclude(user_id__in=admins_notified).select_related('user'):
                _notify(
                    user=m.user,
                    notification_type='contribution_join_request',
                    title=f"Join request — {contribution.title}",
                    message=f"{display} wants to join {contribution.title}. Tap to review.",
                    contribution_id=contribution.id,
                    join_request_id=jr.id,
                )

        return jr

    @staticmethod
    def invite_user(contribution_id, admin, phone):
        from apps.users.models import User

        contribution = Contribution.objects.select_related('community', 'created_by').get(
            id=contribution_id
        )

        require(admin, "contribution.admin", contribution,
                "Only the contribution creator or a community admin can send invitations.")

        if contribution.status != 'active':
            raise ValidationError("This contribution is not accepting new members.")

        try:
            invitee = User.objects.get(phone_number=phone)
        except User.DoesNotExist:
            raise ValidationError(f"No user found with phone number {phone}.")

        if invitee == admin:
            raise ValidationError("You cannot invite yourself.")

        # Respect the invitee's discoverable privacy setting.
        from apps.users.models import PrivacyPreferences
        try:
            prefs = invitee.privacy_prefs
            if not prefs.discoverable:
                raise ValidationError(
                    f"{phone} has restricted who can invite them to contributions."
                )
        except PrivacyPreferences.DoesNotExist:
            pass  # no prefs row → default discoverable=True

        if not ContributionJoinRequestService._is_community_member(contribution, invitee):
            raise ValidationError(f"{phone} is not a member of this community.")

        if ContributionJoinRequestService._already_participant(contribution, invitee):
            raise ValidationError(f"{phone} is already a participant in this contribution.")

        existing = ContributionJoinRequest.objects.filter(
            contribution=contribution, user=invitee
        ).first()
        if existing:
            if existing.status == 'PENDING':
                raise ValidationError(f"{phone} already has a pending request or invitation.")
            if existing.status == 'APPROVED':
                raise ValidationError(f"{phone} is already approved.")
            existing.status       = 'PENDING'
            existing.request_type = 'INVITE'
            existing.invited_by   = admin
            existing.reviewed_at  = None
            existing.reviewed_by  = None
            existing.save()
            jr = existing
        else:
            jr = ContributionJoinRequest.objects.create(
                contribution=contribution,
                user=invitee,
                request_type='INVITE',
                invited_by=admin,
            )

        _notify(
            user=invitee,
            notification_type='contribution_invite',
            title=f"You've been invited — {contribution.title}",
            message=(
                f"{admin.name or admin.phone_number} invited you to join {contribution.title}."
            ),
            contribution_id=contribution.id,
            join_request_id=jr.id,
        )
        return jr

    @staticmethod
    def action_request(request_id, admin, action):
        jr = ContributionJoinRequest.objects.select_related('contribution', 'user').get(
            id=request_id
        )

        if jr.request_type != 'REQUEST':
            raise ValidationError("Use respond_to_invite() for invitation rows.")

        require(admin, "contribution.admin", jr.contribution,
                "Only an admin or the contribution creator can review join requests.")

        if jr.status != 'PENDING':
            raise ValidationError(f"This request has already been {jr.status.lower()}.")

        jr.status      = 'APPROVED' if action == 'approve' else 'REJECTED'
        jr.reviewed_by = admin
        jr.reviewed_at = timezone.now()
        jr.save()

        if action == 'approve':
            ContributionService.join_contribution(jr.contribution_id, jr.user)
            _notify(
                user=jr.user,
                notification_type='contribution_join_approved',
                title=f"Request approved — {jr.contribution.title}",
                message=(
                    f"Your request to join {jr.contribution.title} was approved. "
                    "You're now a participant."
                ),
                contribution_id=jr.contribution_id,
            )
        else:
            _notify(
                user=jr.user,
                notification_type='contribution_join_rejected',
                title=f"Request declined — {jr.contribution.title}",
                message=(
                    f"Your request to join {jr.contribution.title} was not approved."
                ),
                contribution_id=jr.contribution_id,
            )

        return jr

    @staticmethod
    def respond_to_invite(request_id, user, action):
        jr = ContributionJoinRequest.objects.select_related(
            'contribution', 'invited_by'
        ).get(id=request_id)

        if jr.request_type != 'INVITE':
            raise ValidationError("Use action_request() for join request rows.")

        if jr.user != user:
            raise PermissionDenied("You can only respond to your own invitations.")

        if jr.status != 'PENDING':
            raise ValidationError(f"This invitation has already been {jr.status.lower()}.")

        jr.status      = 'APPROVED' if action == 'accept' else 'REJECTED'
        jr.reviewed_by = user
        jr.reviewed_at = timezone.now()
        jr.save()

        if action == 'accept':
            ContributionService.join_contribution(jr.contribution_id, user)
            if jr.invited_by:
                _notify(
                    user=jr.invited_by,
                    notification_type='contribution_invite_accepted',
                    title=f"Invite accepted — {jr.contribution.title}",
                    message=(
                        f"{user.name or user.phone_number} accepted your invitation "
                        f"to join {jr.contribution.title}."
                    ),
                    contribution_id=jr.contribution_id,
                )
        return jr

    @staticmethod
    def get_pending_requests(contribution_id):
        return ContributionJoinRequest.objects.filter(
            contribution_id=contribution_id, request_type='REQUEST', status='PENDING',
        ).select_related('user').order_by('created_at')

    @staticmethod
    def get_my_invite(contribution_id, user):
        return ContributionJoinRequest.objects.filter(
            contribution_id=contribution_id, user=user,
            request_type='INVITE', status='PENDING',
        ).first()

    @staticmethod
    def get_my_request(contribution_id, user):
        return ContributionJoinRequest.objects.filter(
            contribution_id=contribution_id, user=user, request_type='REQUEST',
        ).first()
