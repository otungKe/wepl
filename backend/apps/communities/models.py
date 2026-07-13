import uuid

from django.conf import settings
from django.db import models


def _generate_invite_code() -> str:
    return uuid.uuid4().hex[:10].upper()


class Community(models.Model):

    # Lifecycle (Communities audit CR-2). ACTIVE is the only state in which new
    # money objects, memberships, or conversations may be created. SUSPENDED is
    # an ops-only freeze (fraud investigation / compliance); ARCHIVED is the
    # owner's orderly exit for a community whose cycle is done. Reads stay open
    # in every state — members can always see their history. Hard delete is
    # reserved for never-funded shells (see CommunityService.delete_community).
    class Status(models.TextChoices):
        ACTIVE    = 'active',    'Active'
        SUSPENDED = 'suspended', 'Suspended (ops freeze)'
        ARCHIVED  = 'archived',  'Archived'

    class Category(models.TextChoices):
        SAVINGS    = "savings",    "Savings"
        CHAMA      = "chama",      "Chama / Investment Club"
        INVESTMENT = "investment", "Investment"
        WELFARE    = "welfare",    "Welfare"
        EMERGENCY  = "emergency",  "Emergency Fund"
        BUSINESS   = "business",   "Business"
        GENERAL    = "general",    "General"

    name        = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,           # PROTECT — preserves financial history if creator is deleted
        related_name="created_communities",
    )

    # Multi-tenancy boundary (Phase 6, ADR-0008). Every community belongs to
    # exactly one tenant (a SACCO / hosted institution); stamped on create and
    # backfilled, so the column is now mandatory (P6-05).
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.PROTECT, related_name='communities',
    )

    # Organization spine (ADR-0026): a Community is the first Organization
    # archetype. The Organization row is the general participant entity; this
    # row is its archetype-specific profile. Stamped at creation and backfilled;
    # nullable only so pre-spine rows migrate additively.
    organization = models.OneToOneField(
        'organizations.Organization', null=True, blank=True,
        on_delete=models.PROTECT, related_name='community_profile',
    )

    community_photo = models.ImageField(upload_to="communities/", null=True, blank=True)

    is_private       = models.BooleanField(default=False)
    invite_code      = models.CharField(max_length=20, unique=True, default=_generate_invite_code)
    has_welfare_fund = models.BooleanField(default=False)
    has_shares_fund  = models.BooleanField(default=False)
    category         = models.CharField(max_length=20, choices=Category.choices, default=Category.GENERAL)
    location         = models.CharField(max_length=120, blank=True, default="")
    status           = models.CharField(max_length=10, choices=Status.choices,
                                        default=Status.ACTIVE, db_index=True)
    created_at       = models.DateTimeField(auto_now_add=True)

    # ── Section A: Community Access & Visibility settings ─────────────────────

    class JoinPolicy(models.TextChoices):
        OPEN        = 'open',        'Open — anyone can join directly'
        REQUEST     = 'request',     'Request-to-join — admin approval required'
        INVITE_ONLY = 'invite_only', 'Invite only — via invite link'

    class InvitePermission(models.TextChoices):
        ADMINS  = 'admins',  'Admins & Treasurers only'
        MEMBERS = 'members', 'Any member'
        CREATOR = 'creator', 'Creator only'

    class ContributionPermission(models.TextChoices):
        ADMINS  = 'admins',  'Admins & Treasurers only'
        MEMBERS = 'members', 'Any member'

    class MemberListVisibility(models.TextChoices):
        ALL    = 'all',    'All members'
        ADMINS = 'admins', 'Admins only'

    join_policy              = models.CharField(max_length=15, choices=JoinPolicy.choices,              default=JoinPolicy.INVITE_ONLY)
    invite_permission        = models.CharField(max_length=10, choices=InvitePermission.choices,        default=InvitePermission.ADMINS)
    contribution_permission  = models.CharField(max_length=10, choices=ContributionPermission.choices,  default=ContributionPermission.ADMINS)
    member_list_visibility   = models.CharField(max_length=10, choices=MemberListVisibility.choices,    default=MemberListVisibility.ALL)
    max_members              = models.PositiveIntegerField(null=True, blank=True,
                                   help_text="Maximum number of active members. Null = unlimited.")

    # ── Section B: New Member Cooling-Off Period ───────────────────────────────
    # Number of days a new member must wait before accessing financial features:
    # welfare claims, emergency advances, disbursement votes.
    # 0 = no waiting period. Default = 30 days.
    cooling_off_days = models.PositiveSmallIntegerField(
        default=30,
        help_text="Days a new member must wait before accessing financial features. 0 = none.",
    )

    class Meta:
        indexes = [
            models.Index(fields=["is_private", "category"], name="community_priv_cat_idx"),
        ]

    def __str__(self):
        return self.name

    # ── Helpers ────────────────────────────────────────────────────────────────

    def active_memberships(self):
        return self.memberships.filter(is_active=True)

    def active_admin_count(self) -> int:
        """Admins who can actually act: platform-deactivated users are excluded
        so a banned/deactivated account can never satisfy (or deadlock) the
        last-admin guards (audit G-9)."""
        return self.memberships.filter(
            is_active=True, role=CommunityMembership.Role.ADMIN,
            user__is_active=True,
        ).count()

    def membership_for(self, user):
        """Return the active membership for *user*, or None."""
        if not user or not user.is_authenticated:
            return None
        return self.memberships.filter(user=user, is_active=True).first()


class CommunityMembership(models.Model):

    class Role(models.TextChoices):
        ADMIN     = "admin",     "Admin"
        TREASURER = "treasurer", "Treasurer"
        MEMBER    = "member",    "Member"

    # WHY a membership is (in)active (audit H-4). is_active stays the fast
    # query flag; member_status records the reason and carries the one state
    # with teeth: BANNED members cannot rejoin or re-request — ever — until
    # an owner lifts it (by removing again without ban… deliberately absent;
    # unbanning is a future explicit action).
    class MemberStatus(models.TextChoices):
        ACTIVE  = "active",  "Active"
        LEFT    = "left",    "Left voluntarily"
        REMOVED = "removed", "Removed by owner"
        BANNED  = "banned",  "Banned — cannot rejoin"

    user      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    community = models.ForeignKey(Community, on_delete=models.CASCADE, related_name="memberships")
    role      = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER)
    is_active = models.BooleanField(default=True)
    member_status = models.CharField(max_length=10, choices=MemberStatus.choices,
                                     default=MemberStatus.ACTIVE)
    joined_at = models.DateTimeField(auto_now_add=True)
    # Set whenever an inactive membership is reactivated. The cooling-off clock
    # runs from membership_start (the LATER of joined_at / rejoined_at) so
    # leaving and rejoining can never bypass the waiting period (audit G-4),
    # while joined_at keeps the original tenure for history.
    rejoined_at = models.DateTimeField(null=True, blank=True)
    # When True, this member gets no *push* for this community's activity (the
    # in-app record is still kept). Per-community notification mute.
    notifications_muted = models.BooleanField(default=False)

    class Meta:
        unique_together = ("user", "community")
        indexes = [
            models.Index(fields=["community", "is_active"], name="mem_community_active_idx"),
            models.Index(fields=["user",      "is_active"], name="mem_user_active_idx"),
        ]

    def __str__(self):
        return f"{self.user.phone_number} - {self.community.name}"

    @property
    def membership_start(self):
        """When the CURRENT stint of membership began — cooling-off runs from here."""
        return self.rejoined_at or self.joined_at


class CommunityJoinRequest(models.Model):

    class Status(models.TextChoices):
        PENDING   = "PENDING",   "Pending"
        APPROVED  = "APPROVED",  "Approved"
        REJECTED  = "REJECTED",  "Rejected"
        CANCELLED = "CANCELLED", "Cancelled by requester"

    community  = models.ForeignKey(Community, on_delete=models.CASCADE, related_name="join_requests")
    requester  = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="join_requests",
    )
    status     = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="reviewed_join_requests",
    )

    class Meta:
        # One OPEN request per (community, requester); decided/cancelled rows
        # accumulate as history — a re-request creates a NEW row instead of
        # overwriting the previous decision's reviewer/timestamp (audit M-2).
        constraints = [
            models.UniqueConstraint(
                fields=["community", "requester"],
                condition=models.Q(status="PENDING"),
                name="joinreq_one_pending_per_pair",
            ),
        ]
        indexes = [
            models.Index(fields=["community", "status"], name="joinreq_community_status_idx"),
        ]

    def __str__(self):
        return f"{self.requester.phone_number} → {self.community.name} [{self.status}]"
