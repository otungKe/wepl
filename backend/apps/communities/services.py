"""
Community domain services.

Key changes vs. previous version:
  * join_community now refuses PRIVATE communities directly — the only
    legitimate entry path is invite-code → request → admin-approval
    (which calls join_community with _approved=True). Previously, POST
    /<id>/join/ let anyone bypass approval entirely.
  * State-mutating methods run inside @transaction.atomic with
    select_for_update() to prevent double-approve / double-fire
    notification races from concurrent admin taps.
  * Guards prevent a community being left with zero active admins.
  * _notify_admins() helper removes repetitive queryset boilerplate.
"""
import logging

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.activity.models import Activity
from apps.activity.services import ActivityService
from apps.users.tiers import AccessPolicy
from apps.audit.services import AuditService
from apps.core.policy import require

from .models import Community, CommunityJoinRequest, CommunityMembership

logger = logging.getLogger(__name__)

Role   = CommunityMembership.Role
Status = CommunityJoinRequest.Status


def require_active_community(community, action: str = 'do this') -> None:
    """The lifecycle chokepoint (audit CR-2): creation of memberships, money
    objects, and conversations is only legal while a community is ACTIVE.
    Reads — and money flows that settle existing obligations (advance
    repayments, in-flight callbacks) — are deliberately NOT gated here."""
    if community.status == Community.Status.ACTIVE:
        return
    label = ('suspended pending review' if community.status == Community.Status.SUSPENDED
             else 'archived')
    raise ValidationError(f"This community is {label} — you can't {action} right now.")


def check_cooling_off(user, community, action: str) -> None:
    """
    Raise ValidationError if the user joined *community* too recently
    to perform *action*.

    action values (for the error message):
      'welfare_claim'         — submit a welfare fund claim
      'emergency_advance'     — request an emergency advance
      'disbursement_vote'     — vote on a disbursement request

    No-op when cooling_off_days == 0 or no membership row exists.
    """
    days = getattr(community, 'cooling_off_days', 0)
    if not days:
        return

    membership = CommunityMembership.objects.filter(
        community=community, user=user, is_active=True,
    ).first()
    if not membership:
        return

    from datetime import timedelta
    # membership_start = later of joined_at / rejoined_at, so leaving and
    # rejoining restarts the clock (audit G-4).
    joined   = membership.membership_start
    eligible = joined + timedelta(days=days)

    if timezone.now() < eligible:
        remaining = (eligible - timezone.now()).days + 1
        labels = {
            'welfare_claim':     'submit a welfare claim',
            'emergency_advance': 'request an emergency advance',
            'disbursement_vote': 'vote on disbursement requests',
        }
        label = labels.get(action, 'access this feature')
        raise ValidationError(
            f"New members must wait {days} days before they can {label} in this community. "
            f"You will be eligible in {remaining} day{'s' if remaining != 1 else ''}."
        )


def _dn(user) -> str:
    """Display name — user's name if set, otherwise their phone number."""
    return (user.name or "").strip() or user.phone_number


def _notify_admins(community, *, exclude_user=None, **kwargs):
    """Send a notification to every active admin of *community*.
    Pass exclude_user to skip one (e.g. the action's initiator)."""
    from apps.notifications.services import NotificationService
    qs = community.memberships.filter(role=Role.ADMIN, is_active=True)
    if exclude_user is not None:
        qs = qs.exclude(user=exclude_user)
    for m in qs:
        NotificationService.create(user=m.user, community_id=community.id, **kwargs)


class CommunityService:

    # ── Creation ───────────────────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def create_community(user, validated_data, share_price=None):
        AccessPolicy.gate(user, "Verify your identity to create a community.")
        from apps.tenants.resolve import tenant_for_user
        community = Community.objects.create(
            created_by=user, tenant=tenant_for_user(user), **validated_data,
        )
        CommunityMembership.objects.create(user=user, community=community, role=Role.ADMIN)

        if community.has_welfare_fund:
            from apps.contributions.models import WelfareFund
            WelfareFund.objects.create(
                community=community,
                name=f"{community.name} Welfare Fund",
            )

        if community.has_shares_fund:
            from decimal import Decimal
            from apps.contributions.models import SharesFund, ShareHolding
            price = Decimal(str(share_price)) if share_price else Decimal("100.00")
            fund = SharesFund.objects.create(
                community=community,
                name=f"{community.name} Shares Fund",
                share_price=price,
            )
            ShareHolding.objects.create(shares_fund=fund, user=user)

        logger.info("Community created: '%s' (id=%s) by %s", community.name, community.id, _dn(user))
        ActivityService.record(
            actor=user,
            verb="community_created",
            params={"community_name": community.name},
            visibility=Activity.Visibility.COMMUNITY,
            community=community,
        )
        return community

    # ── Membership ─────────────────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def join_community(user, community, *, _approved=False):
        """
        Add *user* to *community* as an active member.

        PRIVATE communities may not be joined directly — callers must go through
        the invite/request/approval flow, which sets _approved=True.
        Public communities can be joined directly.
        """
        AccessPolicy.gate(user, "Verify your identity to join communities.")
        require_active_community(community, 'join it')
        if community.is_private and not _approved:
            raise PermissionDenied(
                "This community is private. Request to join using an invite code."
            )

        # Lock the community row to prevent concurrent race conditions.
        community = Community.objects.select_for_update().get(pk=community.pk)

        # Enforce member cap
        if community.max_members:
            active_count = community.memberships.filter(is_active=True).count()
            if active_count >= community.max_members:
                raise ValidationError(
                    f"This community has reached its maximum capacity of "
                    f"{community.max_members} members."
                )
        membership, created = CommunityMembership.objects.get_or_create(
            user=user, community=community, defaults={"role": Role.MEMBER},
        )
        if not created and not membership.is_active:
            membership.is_active = True
            membership.role = Role.MEMBER
            # Restart the cooling-off clock: this stint begins now (audit G-4).
            membership.rejoined_at = timezone.now()
            membership.save(update_fields=["is_active", "role", "rejoined_at"])
        elif not created:
            # Already an active member — idempotent no-op, skip duplicate notifications.
            logger.debug("join_community: %s already a member of '%s'", _dn(user), community.name)
            return membership

        logger.info("%s joined community '%s' (id=%s)", _dn(user), community.name, community.id)
        ActivityService.record(
            actor=user,
            verb="community_joined",
            params={"community_name": community.name},
            visibility=Activity.Visibility.COMMUNITY,
            community=community,
        )
        _notify_admins(
            community,
            exclude_user=user,
            notification_type="community_join",
            title=f"New member in {community.name}",
            message=f"{_dn(user)} joined your community.",
        )
        return membership

    @staticmethod
    @transaction.atomic
    def leave_community(user, community):
        membership = (
            CommunityMembership.objects
            .select_for_update()
            .filter(user=user, community=community, is_active=True)
            .first()
        )
        if not membership:
            raise ValidationError("You are not a member of this community.")

        # The owner cannot walk away with rank-4 authority (audit G-1): they'd
        # keep exclusive member-management power from outside while nobody
        # inside could exercise it. Transfer first — the mirror of the
        # last-admin guard below.
        if community.created_by_id == user.id:
            raise ValidationError(
                "You are the community owner. Transfer ownership to another "
                "member before leaving."
            )

        if membership.role == Role.ADMIN and community.active_admin_count() <= 1:
            # Check if removing this admin would deadlock any active contribution
            # that requires admin-only voting.
            from apps.contributions.models import Contribution
            deadlocked = Contribution.objects.filter(
                community=community,
                is_active=True,
                voting_threshold='admins',
            ).exists()
            if deadlocked:
                raise ValidationError(
                    "You are the last admin and this community has active contributions "
                    "requiring admin approval for withdrawals. "
                    "Promote another member to admin, or change the approval threshold "
                    "on those contributions, before leaving."
                )
            raise ValidationError(
                "You are the last admin. Promote another member to admin before leaving."
            )

        membership.is_active = False
        membership.save(update_fields=["is_active"])
        logger.info("%s left community '%s' (id=%s)", _dn(user), community.name, community.id)
        ActivityService.record(
            actor=user,
            verb="community_left",
            params={"community_name": community.name},
            visibility=Activity.Visibility.PRIVATE,
        )
        return membership

    @staticmethod
    def get_members(community):
        return community.memberships.filter(is_active=True).select_related("user")

    @staticmethod
    def is_member(user, community) -> bool:
        if not user or not user.is_authenticated:
            return False
        return community.memberships.filter(user=user, is_active=True).exists()

    # ── Invite / join requests ─────────────────────────────────────────────────

    @staticmethod
    def get_community_by_invite(code):
        if not code:
            return None
        return Community.objects.filter(invite_code__iexact=code.strip()).first()

    @staticmethod
    @transaction.atomic
    def request_to_join(user, community):
        """
        Submit (or re-open) a join request. Returns (request, created).
        Notifies all community admins.
        """
        AccessPolicy.gate(user, "Verify your identity to join communities.")
        require_active_community(community, 'request to join it')
        if CommunityService.is_member(user, community):
            raise ValidationError("You are already a member of this community.")

        req, created = CommunityJoinRequest.objects.get_or_create(
            community=community,
            requester=user,
            defaults={"status": Status.PENDING},
        )
        if not created:
            # Re-lock the existing row before mutating.
            req = CommunityJoinRequest.objects.select_for_update().get(pk=req.pk)
            if req.status == Status.PENDING:
                raise ValidationError("You already have a pending request for this community.")
            # Previously rejected or removed → re-open.
            req.status = Status.PENDING
            req.reviewed_at = None
            req.reviewed_by = None
            req.save(update_fields=["status", "reviewed_at", "reviewed_by"])
            logger.info("Join request re-opened: %s → '%s'", _dn(user), community.name)
        else:
            logger.info("Join request created: %s → '%s'", _dn(user), community.name)

        _notify_admins(
            community,
            notification_type="join_request",
            title=f"Join request — {community.name}",
            message=f"{_dn(user)} wants to join {community.name}. Tap to review.",
            join_request_id=req.id,
        )
        return req, created

    # ── Role management ────────────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def assign_role(creator, community, membership_id, role):
        """Only the community creator can assign roles (ADR-0009 policy)."""
        require(creator, "community.member.assign_role", community,
                "Only the community creator can assign roles.")
        if role not in Role.values:
            raise ValidationError(f"Invalid role '{role}'.")

        membership = (
            CommunityMembership.objects
            .select_for_update()
            .get(id=membership_id, community=community, is_active=True)
        )
        if membership.user_id == creator.id:
            raise ValidationError("Cannot change the creator's own role.")

        # Guard: don't demote the last remaining admin.
        if (membership.role == Role.ADMIN and role != Role.ADMIN
                and community.active_admin_count() <= 1):
            raise ValidationError("Cannot demote the last admin.")

        old_role = membership.role
        membership.role = role
        membership.save(update_fields=["role"])
        logger.info(
            "Role changed for %s in '%s': %s → %s (by %s)",
            _dn(membership.user), community.name, old_role, role, _dn(creator),
        )
        AuditService.log(
            "community.role_changed", actor=creator, target=community, tenant=community.tenant_id,
            metadata={"membership_id": membership.id, "user_id": membership.user_id,
                      "old_role": old_role, "new_role": role},
        )
        return membership

    @staticmethod
    @transaction.atomic
    def remove_member(creator, community, membership_id):
        """Only the community creator can remove other members (ADR-0009 policy)."""
        require(creator, "community.member.remove", community,
                "Only the community creator can remove members.")

        membership = (
            CommunityMembership.objects
            .select_for_update()
            .get(id=membership_id, community=community, is_active=True)
        )
        if membership.user_id == creator.id:
            raise ValidationError("The community owner cannot be removed.")

        membership.is_active = False
        membership.save(update_fields=["is_active"])
        logger.info(
            "Member removed from '%s': %s (by %s)",
            community.name, _dn(membership.user), _dn(creator),
        )
        AuditService.log(
            "community.member_removed", actor=creator, target=community, tenant=community.tenant_id,
            metadata={"membership_id": membership.id, "user_id": membership.user_id},
        )
        return membership

    @staticmethod
    @transaction.atomic
    def transfer_ownership(creator, community, membership_id):
        """Transfer community ownership to another active member (ADR-0011).

        Only the current owner may transfer (policy: community.ownership.transfer;
        platform operators may also act, to recover an orphaned community whose
        owner deleted their account). The new owner must be an active member and is
        promoted to admin; the former owner stays on as an admin, so the community
        is never left unadministrable.
        """
        require(creator, "community.ownership.transfer", community,
                "Only the community owner can transfer ownership.")

        # Lock the community to serialise concurrent transfers.
        community = Community.objects.select_for_update().get(pk=community.pk)

        new_membership = (
            CommunityMembership.objects
            .select_for_update()
            .filter(id=membership_id, community=community, is_active=True)
            .first()
        )
        if not new_membership:
            raise ValidationError("The new owner must be an active member of this community.")
        if new_membership.user_id == community.created_by_id:
            raise ValidationError("This member is already the community owner.")

        old_owner_id = community.created_by_id
        new_owner = new_membership.user

        community.created_by = new_owner
        community.save(update_fields=["created_by"])

        # New owner must hold admin authority.
        if new_membership.role != Role.ADMIN:
            new_membership.role = Role.ADMIN
            new_membership.save(update_fields=["role"])

        # Keep the former owner as an admin member (if they still have one) so the
        # transfer never reduces the admin count — no last-admin lockout.
        former = community.memberships.filter(user_id=old_owner_id, is_active=True).first()
        if former and former.role != Role.ADMIN:
            former.role = Role.ADMIN
            former.save(update_fields=["role"])

        logger.info(
            "Ownership of '%s' (id=%s) transferred %s → %s (by %s)",
            community.name, community.id, old_owner_id, new_owner.id, _dn(creator),
        )
        AuditService.log(
            "community.ownership_transferred", actor=creator, target=community,
            tenant=community.tenant_id,
            metadata={"from_user_id": old_owner_id, "to_user_id": new_owner.id},
        )
        ActivityService.record(
            actor=creator,
            verb="community_ownership_transferred",
            params={"community_name": community.name, "new_owner_name": _dn(new_owner)},
            visibility=Activity.Visibility.COMMUNITY,
            community=community,
        )
        from apps.notifications.services import NotificationService
        NotificationService.create(
            user=new_owner,
            community_id=community.id,
            notification_type="community_ownership",
            title=f"You're now the owner of {community.name}",
            message=f"{_dn(creator)} transferred ownership of {community.name} to you.",
        )
        return community


    # ── Lifecycle (audit CR-1 / CR-2) ─────────────────────────────────────────

    @staticmethod
    def has_financial_history(community) -> bool:
        """True when ANY money object linked to this community has recorded
        movement. Strict on purpose: when in doubt, the community must be
        archived, never deleted."""
        from apps.contributions.models import (
            ContributionTransaction, EmergencyAdvance, ShareHolding,
            WelfareContribution, WelfareClaim,
        )
        if ContributionTransaction.objects.filter(
                contribution__community=community).exists():
            return True
        if EmergencyAdvance.objects.filter(
                contribution__community=community).exists():
            return True
        if WelfareContribution.objects.filter(fund__community=community).exists():
            return True
        if WelfareClaim.objects.filter(fund__community=community).exists():
            return True
        if ShareHolding.objects.filter(
                shares_fund__community=community, total_contributed__gt=0).exists():
            return True
        return False

    @staticmethod
    @transaction.atomic
    def archive_community(actor, community):
        """Owner's orderly exit: freezes joins, money-object creation and new
        conversations while keeping every record readable."""
        require(actor, "community.archive", community,
                "Only the community owner can archive this community.")
        community = Community.objects.select_for_update().get(pk=community.pk)
        if community.status == Community.Status.ARCHIVED:
            raise ValidationError("This community is already archived.")
        if community.status == Community.Status.SUSPENDED:
            raise ValidationError("A suspended community cannot be archived until "
                                  "the suspension is lifted.")
        community.status = Community.Status.ARCHIVED
        community.save(update_fields=["status"])
        AuditService.log("community.archived", actor=actor, target=community,
                         tenant=community.tenant_id)
        ActivityService.record(
            actor=actor, verb="community_archived",
            params={"community_name": community.name},
            visibility=Activity.Visibility.COMMUNITY, community=community,
        )
        return community

    @staticmethod
    @transaction.atomic
    def unarchive_community(actor, community):
        require(actor, "community.archive", community,
                "Only the community owner can restore this community.")
        community = Community.objects.select_for_update().get(pk=community.pk)
        if community.status != Community.Status.ARCHIVED:
            raise ValidationError("This community is not archived.")
        community.status = Community.Status.ACTIVE
        community.save(update_fields=["status"])
        AuditService.log("community.unarchived", actor=actor, target=community,
                         tenant=community.tenant_id)
        return community

    @staticmethod
    @transaction.atomic
    def suspend_community(community, *, actor=None, reason=""):
        """Ops-only freeze (fraud investigation / compliance / court order).
        Not exposed to any customer role — callers are the Django admin action
        and, later, the Back Office console."""
        community = Community.objects.select_for_update().get(pk=community.pk)
        if community.status == Community.Status.SUSPENDED:
            raise ValidationError("This community is already suspended.")
        previous = community.status
        community.status = Community.Status.SUSPENDED
        community.save(update_fields=["status"])
        AuditService.log("community.suspended", actor=actor, target=community,
                         tenant=community.tenant_id,
                         metadata={"reason": reason, "previous_status": previous})
        logger.warning("Community '%s' (id=%s) SUSPENDED: %s",
                       community.name, community.id, reason or "no reason recorded")
        return community

    @staticmethod
    @transaction.atomic
    def unsuspend_community(community, *, actor=None, reason=""):
        community = Community.objects.select_for_update().get(pk=community.pk)
        if community.status != Community.Status.SUSPENDED:
            raise ValidationError("This community is not suspended.")
        community.status = Community.Status.ACTIVE
        community.save(update_fields=["status"])
        AuditService.log("community.unsuspended", actor=actor, target=community,
                         tenant=community.tenant_id, metadata={"reason": reason})
        return community

    @staticmethod
    @transaction.atomic
    def delete_community(actor, community):
        """Hard delete — legal ONLY for never-funded shells (audit CR-1).

        Any recorded financial movement makes the community permanent: the
        ledger's journal lines reference these domain objects, and destroying
        the context of posted money is indefensible. The exit for a real
        community is archive_community(). Empty auto-created funds are removed
        first so PROTECT doesn't block the legitimate shell case.
        """
        require(actor, "community.delete", community,
                "Only the creator can delete this community.")
        community = Community.objects.select_for_update().get(pk=community.pk)

        if CommunityService.has_financial_history(community):
            raise ValidationError(
                "This community has financial history and cannot be deleted. "
                "Archive it instead — records stay readable and nothing is lost."
            )

        from apps.contributions.models import Contribution, SharesFund, WelfareFund
        # Zero-movement money shells (auto-created at birth or never used);
        # holdings/participants cascade with their fund rows.
        WelfareFund.objects.filter(community=community).delete()
        SharesFund.objects.filter(community=community).delete()
        Contribution.objects.filter(community=community).delete()

        AuditService.log(
            "community.deleted", actor=actor, target_type="community",
            target_id=str(community.id), tenant=community.tenant_id,
            metadata={"name": community.name},
        )
        # Log the actor by id, not display name — _dn falls back to the phone
        # number, which must not land in clear-text logs.
        logger.info("Community '%s' (id=%s) deleted by user %s",
                    community.name, community.id, actor.pk)
        community.delete()

    # ── Join request actions ───────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def action_join_request(admin_user, request_id, action):
        """
        action: 'approve' | 'reject'
        Locked with select_for_update() to prevent double-processing from
        concurrent admin taps.
        """
        req = (
            CommunityJoinRequest.objects
            .select_for_update()
            .select_related("community", "requester")
            .get(id=request_id)
        )

        require(admin_user, "community.join_request.review", req.community,
                "Only admins can review join requests.")

        if req.status != Status.PENDING:
            raise ValidationError("This request has already been reviewed.")

        req.status = Status.APPROVED if action == "approve" else Status.REJECTED
        req.reviewed_by = admin_user
        req.reviewed_at = timezone.now()
        req.save(update_fields=["status", "reviewed_by", "reviewed_at"])

        logger.info(
            "Join request %s: %s → '%s' (by %s)",
            req.status, _dn(req.requester), req.community.name, _dn(admin_user),
        )

        from apps.notifications.services import NotificationService
        if action == "approve":
            CommunityService.join_community(req.requester, req.community, _approved=True)
            NotificationService.create(
                user=req.requester,
                notification_type="join_approved",
                title=f"Request approved — {req.community.name}",
                message=f"Welcome! You're now a member of {req.community.name}.",
                community_id=req.community.id,
            )
        else:
            NotificationService.create(
                user=req.requester,
                notification_type="join_rejected",
                title=f"Request declined — {req.community.name}",
                message=f"Your request to join {req.community.name} was not approved.",
                community_id=req.community.id,
            )
        return req
