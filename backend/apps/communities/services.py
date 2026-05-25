from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from .models import Community, CommunityMembership, CommunityJoinRequest
from apps.activity.services import ActivityService


def _dn(user) -> str:
    """Return the user's display name, falling back to their phone number."""
    return (user.name or "").strip() or user.phone_number


class CommunityService:

    @staticmethod
    def create_community(user, validated_data, share_price=None):
        community = Community.objects.create(created_by=user, **validated_data)
        CommunityMembership.objects.create(user=user, community=community, role='admin')

        if community.has_welfare_fund:
            from apps.contributions.models import WelfareFund
            WelfareFund.objects.create(
                community=community,
                name=f"{community.name} Welfare Fund",
            )

        if community.has_shares_fund:
            from decimal import Decimal
            from apps.contributions.models import SharesFund, ShareHolding
            price = Decimal(str(share_price)) if share_price else Decimal('100.00')
            fund = SharesFund.objects.create(
                community=community,
                name=f"{community.name} Shares Fund",
                share_price=price,
            )
            ShareHolding.objects.create(shares_fund=fund, user=user)

        ActivityService.log_activity(
            user=user,
            activity_type='community_created',
            message=f"{_dn(user)} created community '{community.name}'"
        )
        return community

    @staticmethod
    def join_community(user, community):
        membership, created = CommunityMembership.objects.get_or_create(
            user=user, community=community, defaults={'role': 'member'}
        )
        if not created:
            membership.is_active = True
            membership.role = 'member'
            membership.save()

        ActivityService.log_activity(
            user=user,
            activity_type='community_joined',
            message=f"{_dn(user)} joined '{community.name}'"
        )

        from apps.notifications.services import NotificationService
        admins = CommunityMembership.objects.filter(
            community=community, role='admin', is_active=True
        ).exclude(user=user)
        for admin in admins:
            NotificationService.create(
                user=admin.user,
                notification_type='community_join',
                title=f"New member in {community.name}",
                message=f"{_dn(user)} joined your community.",
                community_id=community.id,
            )
        return membership

    @staticmethod
    def leave_community(user, community):
        membership = CommunityMembership.objects.filter(user=user, community=community).first()
        if membership:
            membership.is_active = False
            membership.save()
        ActivityService.log_activity(
            user=user,
            activity_type='community_left',
            message=f"{_dn(user)} left '{community.name}'"
        )
        return membership

    @staticmethod
    def get_members(community):
        return CommunityMembership.objects.filter(community=community, is_active=True)

    @staticmethod
    def is_member(user, community):
        return CommunityMembership.objects.filter(
            user=user, community=community, is_active=True
        ).exists()

    # -----------------------------------------------------------------------
    # Join requests (invite-code based)
    # -----------------------------------------------------------------------

    @staticmethod
    def get_community_by_invite(code):
        return Community.objects.filter(invite_code__iexact=code.strip()).first()

    @staticmethod
    def request_to_join(user, community):
        """
        Submit a join request. Returns (request, created).
        Notifies all admins.
        """
        if CommunityService.is_member(user, community):
            raise ValidationError("You are already a member of this community.")

        req, created = CommunityJoinRequest.objects.get_or_create(
            community=community,
            requester=user,
            defaults={'status': 'PENDING'},
        )

        if not created:
            if req.status == 'PENDING':
                raise ValidationError("You already have a pending request for this community.")
            # APPROVED but no longer active (removed) or REJECTED → allow re-request
            req.status = 'PENDING'
            req.reviewed_at = None
            req.reviewed_by = None
            req.save()

        from apps.notifications.services import NotificationService
        admins = CommunityMembership.objects.filter(
            community=community, role='admin', is_active=True
        )
        for admin in admins:
            NotificationService.create(
                user=admin.user,
                notification_type='join_request',
                title=f"Join request — {community.name}",
                message=f"{_dn(user)} wants to join {community.name}. Tap to review.",
                community_id=community.id,
                join_request_id=req.id,
            )

        return req, created

    @staticmethod
    def assign_role(creator, community, membership_id, role):
        """Only the community creator can assign roles to other members."""
        if community.created_by != creator:
            raise PermissionDenied("Only the community creator can assign roles.")
        if role not in ('admin', 'member', 'treasurer'):
            raise ValidationError(f"Invalid role '{role}'.")
        membership = CommunityMembership.objects.get(id=membership_id, community=community, is_active=True)
        if membership.user == creator:
            raise ValidationError("Cannot change the creator's own role.")
        membership.role = role
        membership.save()
        return membership

    @staticmethod
    def remove_member(creator, community, membership_id):
        """Only the community creator can remove other members."""
        if community.created_by != creator:
            raise PermissionDenied("Only the community creator can remove members.")
        membership = CommunityMembership.objects.get(id=membership_id, community=community, is_active=True)
        if membership.user == creator:
            raise ValidationError("The community owner cannot be removed.")
        membership.is_active = False
        membership.save()
        return membership

    @staticmethod
    def action_join_request(admin_user, request_id, action):
        """action: 'approve' | 'reject'"""
        req = CommunityJoinRequest.objects.select_related('community', 'requester').get(id=request_id)

        is_admin = CommunityMembership.objects.filter(
            community=req.community, user=admin_user, role='admin', is_active=True
        ).exists()
        if not is_admin:
            raise PermissionDenied("Only admins can review join requests.")

        if req.status != 'PENDING':
            raise ValidationError("This request has already been reviewed.")

        req.status = 'APPROVED' if action == 'approve' else 'REJECTED'
        req.reviewed_by = admin_user
        req.reviewed_at = timezone.now()
        req.save()

        from apps.notifications.services import NotificationService

        if action == 'approve':
            CommunityService.join_community(req.requester, req.community)
            NotificationService.create(
                user=req.requester,
                notification_type='join_approved',
                title=f"Request approved — {req.community.name}",
                message=f"Welcome! You're now a member of {req.community.name}.",
                community_id=req.community.id,
            )
        else:
            NotificationService.create(
                user=req.requester,
                notification_type='join_rejected',
                title=f"Request declined — {req.community.name}",
                message=f"Your request to join {req.community.name} was not approved.",
                community_id=req.community.id,
            )

        return req
