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


def _require_same_tenant(user, community) -> None:
    """Cross-tenant membership guard (audit G-13/M-3). A no-op while every
    user resolves to the default tenant; the moment P6-04 maps users to real
    institutions, every join path inherits this refusal + audit trail."""
    from apps.tenants.resolve import tenant_for_user
    if community.tenant_id and tenant_for_user(user).id != community.tenant_id:
        # The raise rolls back the surrounding service transaction, so a DB
        # audit row written here would vanish with it — the structured log
        # line (request_id/tenant/actor context, ADR-0020) is the durable
        # forensic record for refused attempts.
        logger.warning(
            "Cross-tenant join refused: user %s -> community %s (tenant %s)",
            user.pk, community.id, community.tenant_id,
        )
        raise PermissionDenied("This community belongs to a different institution.")


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


def _notify_admins(community, *, exclude_user=None, notification_type, title,
                   message, **extra):
    """Notify every active admin of *community* via the durable event bus
    (ADR-0006, audit H-5): one outbox event per admin, written in the current
    transaction — a rollback discards them, a crash never loses them, and
    delivery (Notification row + push) happens async in the relay."""
    from apps.core.events import emit
    qs = community.memberships.filter(role=Role.ADMIN, is_active=True,
                                      user__is_active=True)
    if exclude_user is not None:
        qs = qs.exclude(user=exclude_user)
    for m in qs:
        emit(notification_type, user_id=m.user_id, title=title, message=message,
             community_id=community.id, **extra)


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
        # Organization spine (ADR-0026): every community is born as an
        # Organization of archetype 'community'.
        from apps.organizations.models import ensure_organization_for_community
        ensure_organization_for_community(community)
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

        logger.info("Community created: '%s' (id=%s) by user %s", community.name, community.id, user.pk)
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
        _require_same_tenant(user, community)
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
        if not created and membership.member_status == CommunityMembership.MemberStatus.BANNED:
            raise PermissionDenied("You cannot rejoin this community.")
        if not created and not membership.is_active:
            membership.is_active = True
            membership.role = Role.MEMBER
            membership.member_status = CommunityMembership.MemberStatus.ACTIVE
            # Restart the cooling-off clock: this stint begins now (audit G-4).
            membership.rejoined_at = timezone.now()
            membership.save(update_fields=["is_active", "role", "member_status", "rejoined_at"])
        elif not created:
            # Already an active member — idempotent no-op, skip duplicate notifications.
            logger.debug("join_community: user %s already a member of '%s'", user.pk, community.name)
            return membership

        logger.info("User %s joined community '%s' (id=%s)", user.pk, community.name, community.id)
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
        membership.member_status = CommunityMembership.MemberStatus.LEFT
        membership.save(update_fields=["is_active", "member_status"])
        logger.info("User %s left community '%s' (id=%s)", user.pk, community.name, community.id)
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
        _require_same_tenant(user, community)
        if CommunityService.is_member(user, community):
            raise ValidationError("You are already a member of this community.")
        if community.memberships.filter(
                user=user,
                member_status=CommunityMembership.MemberStatus.BANNED).exists():
            raise PermissionDenied("You cannot rejoin this community.")

        # History-preserving (audit M-2): a re-request creates a NEW row —
        # never re-opens a decided one, so past reviews keep their reviewer
        # and timestamp. The partial unique constraint (one PENDING per pair)
        # backstops the existence check under concurrency.
        if CommunityJoinRequest.objects.filter(
                community=community, requester=user, status=Status.PENDING).exists():
            raise ValidationError("You already have a pending request for this community.")
        req = CommunityJoinRequest.objects.create(
            community=community, requester=user, status=Status.PENDING,
        )
        created = True
        logger.info("Join request created: user %s -> '%s'", user.pk, community.name)

        _notify_admins(
            community,
            notification_type="join_request",
            title=f"Join request — {community.name}",
            message=f"{_dn(user)} wants to join {community.name}. Tap to review.",
            join_request_id=req.id,
        )
        return req, created

    @staticmethod
    @transaction.atomic
    def cancel_join_request(user, request_id):
        """Requester withdraws their own PENDING request (audit M-2/G-10)."""
        req = (CommunityJoinRequest.objects.select_for_update()
               .filter(id=request_id, requester=user).first())
        if req is None:
            raise ValidationError("Request not found.")
        if req.status != Status.PENDING:
            raise ValidationError("Only a pending request can be cancelled.")
        req.status = Status.CANCELLED
        req.reviewed_at = timezone.now()
        req.save(update_fields=["status", "reviewed_at"])
        logger.info("Join request %s cancelled by requester user %s", req.id, user.pk)
        return req

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
            "Role changed for user %s in '%s': %s -> %s (by user %s)",
            membership.user_id, community.name, old_role, role, creator.pk,
        )
        AuditService.log(
            "community.role_changed", actor=creator, target=community, tenant=community.tenant_id,
            metadata={"membership_id": membership.id, "user_id": membership.user_id,
                      "old_role": old_role, "new_role": role},
        )
        from apps.core.events import emit
        emit(
            "community_role_changed",
            user_id=membership.user_id,
            community_id=community.id,
            title=f"Your role in {community.name} changed",
            message=f"You are now a {membership.get_role_display().lower()} "
                    f"in {community.name}.",
        )
        return membership

    @staticmethod
    @transaction.atomic
    def remove_member(creator, community, membership_id, *, ban=False):
        """Only the community creator can remove other members (ADR-0009 policy).

        ``ban=True`` (audit H-4) marks the membership BANNED: the person can
        never rejoin or re-request — the plain-removal revolving door is shut
        for the cases where it matters.
        """
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
        membership.member_status = (CommunityMembership.MemberStatus.BANNED if ban
                                    else CommunityMembership.MemberStatus.REMOVED)
        membership.save(update_fields=["is_active", "member_status"])
        logger.info(
            "Member %s from '%s': user %s (by user %s)",
            "banned" if ban else "removed", community.name,
            membership.user_id, creator.pk,
        )
        AuditService.log(
            "community.member_banned" if ban else "community.member_removed",
            actor=creator, target=community, tenant=community.tenant_id,
            metadata={"membership_id": membership.id, "user_id": membership.user_id},
        )
        # Silent removal was an audit finding: the person deserves to know.
        # Bans use the same wording on purpose — the ban itself is internal.
        from apps.core.events import emit
        emit(
            "community_removed",
            user_id=membership.user_id,
            community_id=community.id,
            title=f"Membership update — {community.name}",
            message=f"You are no longer a member of {community.name}.",
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
            "Ownership of '%s' (id=%s) transferred %s -> %s (by user %s)",
            community.name, community.id, old_owner_id, new_owner.id, creator.pk,
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
        from apps.core.events import emit
        emit(
            "community_ownership",
            user_id=new_owner.id,
            community_id=community.id,
            title=f"You're now the owner of {community.name}",
            message=f"{_dn(creator)} transferred ownership of {community.name} to you.",
        )
        return community


    # ── Governance settings & invites (audit H-3 / M-1) ──────────────────────

    # The settings a community may edit after creation. Single source of truth
    # for the update endpoint.
    EDITABLE_SETTINGS = frozenset({
        "name", "description", "is_private", "category", "location",
        "join_policy", "invite_permission", "contribution_permission",
        "member_list_visibility", "max_members", "cooling_off_days",
    })

    @staticmethod
    @transaction.atomic
    def update_settings(actor, community, payload: dict):
        """Apply governance/profile changes with a full old→new audit diff —
        flipping join_policy or invite_permission is security-relevant and must
        leave a trail (audit M-1)."""
        require(actor, "community.update", community,
                "Only the creator or an admin can edit community details.")
        payload = {k: v for k, v in payload.items()
                   if k in CommunityService.EDITABLE_SETTINGS}
        if not payload:
            raise ValidationError(
                f"No valid fields provided. Editable: "
                f"{sorted(CommunityService.EDITABLE_SETTINGS)}"
            )

        community = Community.objects.select_for_update().get(pk=community.pk)

        # Guard: can't reduce max_members below current active member count.
        if payload.get("max_members") is not None:
            active = community.memberships.filter(is_active=True).count()
            if int(payload["max_members"]) < active:
                raise ValidationError(
                    f"max_members ({payload['max_members']}) cannot be less than "
                    f"the current active member count ({active})."
                )

        from .serializers import CommunityWriteSerializer
        old = {k: getattr(community, k) for k in payload}
        serializer = CommunityWriteSerializer(community, data=payload, partial=True)
        serializer.is_valid(raise_exception=True)
        community = serializer.save()

        diff = {k: {"old": str(old[k]), "new": str(getattr(community, k))}
                for k in payload if str(old[k]) != str(getattr(community, k))}
        if diff:
            AuditService.log(
                "community.settings_updated", actor=actor, target=community,
                tenant=community.tenant_id, metadata={"changes": diff},
            )
        logger.info("Community '%s' (id=%s) settings updated by user %s: %s",
                    community.name, community.id, actor.pk, sorted(diff))
        return community

    @staticmethod
    @transaction.atomic
    def rotate_invite_code(actor, community):
        """Regenerate the invite code (audit H-3): a leaked code is now
        recoverable. Rotation authority follows the sharing setting — when
        invite_permission is 'creator', only the creator may rotate."""
        from .models import _generate_invite_code
        from .policies import can_see_invite_code

        require(actor, "community.invite.rotate", community,
                "Only admins can rotate the invite code.")
        if not can_see_invite_code(actor, community):
            raise PermissionDenied(
                "Invite sharing is restricted to the creator in this community.")

        community = Community.objects.select_for_update().get(pk=community.pk)
        community.invite_code = _generate_invite_code()
        community.save(update_fields=["invite_code"])
        AuditService.log("community.invite_rotated", actor=actor, target=community,
                         tenant=community.tenant_id)
        logger.info("Invite code rotated for community '%s' (id=%s) by user %s",
                    community.name, community.id, actor.pk)
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
            "Join request %s: user %s -> '%s' (by user %s)",
            req.status, req.requester_id, req.community.name, admin_user.pk,
        )

        from apps.core.events import emit
        if action == "approve":
            CommunityService.join_community(req.requester, req.community, _approved=True)
            emit(
                "join_approved",
                user_id=req.requester_id,
                title=f"Request approved — {req.community.name}",
                message=f"Welcome! You're now a member of {req.community.name}.",
                community_id=req.community.id,
            )
        else:
            emit(
                "join_rejected",
                user_id=req.requester_id,
                title=f"Request declined — {req.community.name}",
                message=f"Your request to join {req.community.name} was not approved.",
                community_id=req.community.id,
            )
        return req
