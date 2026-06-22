import uuid

from django.conf import settings
from django.db import models


def _generate_invite_code() -> str:
    return uuid.uuid4().hex[:10].upper()


class Community(models.Model):

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

    community_photo = models.ImageField(upload_to="communities/", null=True, blank=True)

    is_private       = models.BooleanField(default=False)
    invite_code      = models.CharField(max_length=20, unique=True, default=_generate_invite_code)
    has_welfare_fund = models.BooleanField(default=False)
    has_shares_fund  = models.BooleanField(default=False)
    category         = models.CharField(max_length=20, choices=Category.choices, default=Category.GENERAL)
    location         = models.CharField(max_length=120, blank=True, default="")
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
        return self.memberships.filter(is_active=True, role=CommunityMembership.Role.ADMIN).count()

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

    user      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    community = models.ForeignKey(Community, on_delete=models.CASCADE, related_name="memberships")
    role      = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER)
    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "community")
        indexes = [
            models.Index(fields=["community", "is_active"], name="mem_community_active_idx"),
            models.Index(fields=["user",      "is_active"], name="mem_user_active_idx"),
        ]

    def __str__(self):
        return f"{self.user.phone_number} - {self.community.name}"


class CommunityJoinRequest(models.Model):

    class Status(models.TextChoices):
        PENDING  = "PENDING",  "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

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
        unique_together = ("community", "requester")
        indexes = [
            models.Index(fields=["community", "status"], name="joinreq_community_status_idx"),
        ]

    def __str__(self):
        return f"{self.requester.phone_number} → {self.community.name} [{self.status}]"
