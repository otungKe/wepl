"""Savings pools and who is in them — the root of the whole domain."""

import secrets

from django.conf import settings
from django.db import models

from apps.communities.models import Community

def _generate_invite_code():
    return secrets.token_urlsafe(8)[:12]


# 0001_initial serialises this default by its dotted path, as
# ``apps.contributions.models._generate_invite_code``. Splitting models.py into a
# package moved the function's real home here, which would make a future
# makemigrations write the new path into a fresh AlterField for a callable that
# has not changed. Pinning __module__ keeps the serialised path the historical
# one — still importable, because __init__ re-exports the name.
_generate_invite_code.__module__ = 'apps.contributions.models'


class Contribution(models.Model):

    # Program spine (ADR-0026): this fund is the archetype profile of a Program.
    # Stamped at creation, backfilled for pre-spine rows (hence nullable).
    program = models.OneToOneField(
        'organizations.Program', null=True, blank=True,
        on_delete=models.PROTECT, related_name='contribution_profile',
    )

    VISIBILITY_CHOICES = (
        ('closed', 'Closed'),
        ('open',   'Open'),
    )
    TENURE_CHOICES = (
        ('open',   'Open (no end date)'),
        ('date',   'Until a specific date'),
        ('period', 'Fixed period'),
    )
    FREQUENCY_CHOICES = (
        ('daily',   'Daily'),
        ('weekly',  'Weekly'),
        ('monthly', 'Monthly'),
        ('anytime', 'Anytime'),
    )
    AMOUNT_TYPE_CHOICES = (
        ('fixed', 'Fixed amount per member'),
        ('open',  'Open (any amount)'),
    )
    VOTING_THRESHOLD_CHOICES = (
        ('admins', 'Admins only'),
        ('25',     '25% of members'),
        ('50',     '50% of members'),
        ('100',    '100% of members'),
    )

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)

    visibility = models.CharField(max_length=10, choices=VISIBILITY_CHOICES, default='closed')

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='created_contributions'
    )
    # PROTECT (audit CR-1): a community with financial objects can never be
    # hard-deleted out from under them; deletion of never-funded shells clears
    # these rows first via CommunityService.delete_community.
    community = models.ForeignKey(
        Community, on_delete=models.PROTECT,
        related_name='contributions', null=True, blank=True,
    )
    invite_code = models.CharField(max_length=20, unique=True, default=_generate_invite_code)

    target_amount        = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    # Per-member personal target: amount each individual participant should
    # reach by the end date. Separate from target_amount (the pool total).
    member_target_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    # Term / tenure
    tenure_type   = models.CharField(max_length=10, choices=TENURE_CHOICES, default='open')
    end_date      = models.DateField(null=True, blank=True)
    period_months = models.PositiveIntegerField(null=True, blank=True)

    # Schedule
    frequency   = models.CharField(max_length=10, choices=FREQUENCY_CHOICES, default='anytime')
    amount_type = models.CharField(max_length=10, choices=AMOUNT_TYPE_CHOICES, default='open')
    fixed_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    # Governance — disbursement voting
    voting_threshold = models.CharField(
        max_length=10, choices=VOTING_THRESHOLD_CHOICES, default='admins'
    )

    # ── Section C: Contribution Governance settings ───────────────────────────

    # 1. Transaction visibility — who can see each other's payments
    TX_VIS_CHOICES = (
        ('all',        'All participants see all transactions'),
        ('own',        'Each member sees only their own transactions'),
        ('admins_all', 'Admins see all; members see their own only'),
    )
    transaction_visibility = models.CharField(
        max_length=15, choices=TX_VIS_CHOICES, default='all'
    )

    # 2. Who can propose amendments to contribution settings
    AMENDMENT_PROPOSER_CHOICES = (
        ('creator', 'Creator only'),
        ('admins',  'Admins and treasurers'),
        ('members', 'Any active participant'),
    )
    amendment_proposer = models.CharField(
        max_length=10, choices=AMENDMENT_PROPOSER_CHOICES, default='creator'
    )

    # 3. Amendment voting threshold (separate from disbursement threshold)
    amendment_voting_threshold = models.CharField(
        max_length=10, choices=VOTING_THRESHOLD_CHOICES, default='admins',
        help_text="Threshold to approve a contribution amendment proposal.",
    )

    # 4. Late contribution policy — what happens after the end_date
    LATE_CONTRIBUTION_CHOICES = (
        ('open',   'Allow contributions anytime'),
        ('strict', 'Block contributions after end date'),
        ('grace',  'Allow during a grace period after end date'),
    )
    late_contribution_policy    = models.CharField(
        max_length=10, choices=LATE_CONTRIBUTION_CHOICES, default='open'
    )
    late_contribution_grace_days = models.PositiveSmallIntegerField(
        default=7,
        help_text="Days after end_date that contributions are still accepted (grace policy only).",
    )

    # Legacy fields kept for backwards compatibility
    contribution_type = models.CharField(max_length=20, default='POOL', blank=True)
    cycle_amount      = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    min_approvals     = models.PositiveIntegerField(default=2)
    deadline          = models.DateTimeField(null=True, blank=True)

    STATUS_CHOICES = (
        ('active',   'Active'),
        ('closed',   'Closed'),
        ('archived', 'Archived'),
    )

    is_active   = models.BooleanField(default=True)
    status      = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    is_campaign = models.BooleanField(
        default=False,
        help_text='Marks this as a public fundraising campaign (visible in Discover).',
    )

    # Set by AmendmentService._apply() whenever voting_threshold changes.
    # Prevents disbursements approved under the old (possibly stricter) threshold
    # from executing immediately after governance is relaxed (Issue 16).
    governance_locked_until = models.DateTimeField(
        null=True, blank=True,
        help_text='Disbursements cannot execute until this timestamp passes after a governance change.',
    )

    created_at  = models.DateTimeField(auto_now_add=True)

    def required_approvals(self):
        """Approvals a payout or pool spend needs under ``voting_threshold``
        (``governance.required_approvals``)."""
        from ..governance import required_approvals
        return required_approvals(self, self.voting_threshold)

    class Meta:
        indexes = [
            models.Index(fields=['community', 'is_active'],  name='contrib_comm_active_idx'),
            models.Index(fields=['visibility', 'is_active'], name='contrib_vis_active_idx'),
        ]

    def __str__(self):
        return self.title



class ContributionParticipant(models.Model):
    contribution = models.ForeignKey(
        Contribution, on_delete=models.CASCADE, related_name='participants'
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    joined_at  = models.DateTimeField(auto_now_add=True)
    is_active  = models.BooleanField(default=True)

    class Meta:
        unique_together = ['contribution', 'user']
        indexes = [
            models.Index(fields=['contribution', 'is_active'], name='contrib_participant_active_idx'),
            models.Index(fields=['user', 'is_active'],         name='contrib_part_user_act_idx'),
        ]

    def __str__(self):
        return f"{self.user.phone_number} -> {self.contribution.title}"


# ---------------------------------------------------------------------------
# Shares Fund (optional, per contribution group)
# ---------------------------------------------------------------------------
