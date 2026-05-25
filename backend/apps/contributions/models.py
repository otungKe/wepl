import math
import secrets
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.communities.models import Community
from apps.core.exceptions import TransitionError


def _generate_invite_code():
    return secrets.token_urlsafe(8)[:12]


class Contribution(models.Model):

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
    community = models.ForeignKey(
        Community, on_delete=models.CASCADE,
        related_name='contributions', null=True, blank=True,
    )
    invite_code = models.CharField(max_length=20, unique=True, default=_generate_invite_code)

    target_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    current_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Term / tenure
    tenure_type   = models.CharField(max_length=10, choices=TENURE_CHOICES, default='open')
    end_date      = models.DateField(null=True, blank=True)
    period_months = models.PositiveIntegerField(null=True, blank=True)

    # Schedule
    frequency   = models.CharField(max_length=10, choices=FREQUENCY_CHOICES, default='anytime')
    amount_type = models.CharField(max_length=10, choices=AMOUNT_TYPE_CHOICES, default='open')
    fixed_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    # Governance
    voting_threshold = models.CharField(
        max_length=10, choices=VOTING_THRESHOLD_CHOICES, default='admins'
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
    created_at  = models.DateTimeField(auto_now_add=True)

    def required_approvals(self):
        """Compute required approvals from voting_threshold + live member count."""
        total = self.participants.filter(is_active=True).count()
        t = self.voting_threshold
        if t == 'admins':
            # Any single admin/treasurer approval is sufficient
            return 1
        elif t == '25':
            return max(1, math.ceil(total * 0.25))
        elif t == '50':
            return max(1, math.ceil(total * 0.50))
        elif t == '100':
            return max(1, total)
        return 1

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


class ContributionAccount(models.Model):
    contribution = models.OneToOneField(
        Contribution, on_delete=models.CASCADE, related_name='account'
    )
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    updated_at   = models.DateTimeField(auto_now=True)


class ContributionBalance(models.Model):
    contribution = models.ForeignKey(
        Contribution, on_delete=models.CASCADE, related_name='balances'
    )
    user   = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        unique_together = ['contribution', 'user']
        indexes = [
            models.Index(fields=['contribution', 'user'], name='contrib_bal_user_idx'),
        ]


class ContributionTransaction(models.Model):
    TRANSACTION_TYPES = (
        ('CONTRIBUTION', 'Contribution'),
        ('WITHDRAWAL',   'Withdrawal'),
        ('ADVANCE',      'Advance'),
        ('REPAYMENT',    'Repayment'),
    )
    contribution     = models.ForeignKey(Contribution, on_delete=models.CASCADE, related_name='transactions')
    user             = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    amount           = models.DecimalField(max_digits=12, decimal_places=2)
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    note             = models.CharField(max_length=255, blank=True, null=True)
    mpesa_receipt    = models.CharField(max_length=50, null=True, blank=True)
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['contribution', '-created_at'], name='contrib_tx_contrib_date_idx'),
            models.Index(fields=['user',         '-created_at'], name='contrib_tx_user_date_idx'),
        ]


# ---------------------------------------------------------------------------
# Shares Fund (optional, per contribution group)
# ---------------------------------------------------------------------------

class SharesFund(models.Model):
    community = models.OneToOneField(
        'communities.Community', on_delete=models.CASCADE, related_name='shares_fund',
        null=True, blank=True,
    )
    name        = models.CharField(max_length=255, default='Shares Fund')
    share_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('100.00'))
    total_pool  = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at  = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.community.name if self.community else '?'} — {self.name}"


class ShareHolding(models.Model):
    shares_fund       = models.ForeignKey(SharesFund, on_delete=models.CASCADE, related_name='holdings')
    user              = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    shares_count      = models.DecimalField(max_digits=16, decimal_places=4, default=0)
    total_contributed = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        unique_together = ['shares_fund', 'user']

    @property
    def ownership_pct(self):
        if not self.shares_fund.total_pool:
            return Decimal('0')
        return (self.total_contributed / self.shares_fund.total_pool * 100).quantize(Decimal('0.01'))

    def __str__(self):
        return f"{self.user.phone_number} | {self.shares_count} shares"


# ---------------------------------------------------------------------------
# ROSCA (Rotating Savings)
# ---------------------------------------------------------------------------

class ROSCASlot(models.Model):
    contribution = models.ForeignKey(Contribution, on_delete=models.CASCADE, related_name='rosca_slots')
    participant  = models.ForeignKey(ContributionParticipant, on_delete=models.CASCADE, related_name='rosca_slots')
    slot_order   = models.PositiveIntegerField()
    cycle_number = models.PositiveIntegerField(default=1)
    has_received = models.BooleanField(default=False)
    received_at  = models.DateTimeField(null=True, blank=True)
    payout_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        unique_together = ['contribution', 'slot_order', 'cycle_number']
        ordering = ['cycle_number', 'slot_order']

    def __str__(self):
        return (
            f"{self.contribution.title} | Cycle {self.cycle_number} "
            f"| Slot {self.slot_order} | {self.participant.user.phone_number}"
        )


# ---------------------------------------------------------------------------
# Standing Orders (scheduled automatic payouts)
# ---------------------------------------------------------------------------

class StandingOrder(models.Model):
    FREQUENCY_CHOICES = (
        ('daily',   'Daily'),
        ('weekly',  'Weekly'),
        ('monthly', 'Monthly'),
    )
    PAYEE_TYPE_CHOICES = (
        ('fixed',    'Fixed Payee'),
        ('rotating', 'Rotating Payees'),
    )

    contribution      = models.ForeignKey(Contribution, on_delete=models.CASCADE, related_name='standing_orders')
    created_by        = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    amount            = models.DecimalField(max_digits=12, decimal_places=2)
    frequency         = models.CharField(max_length=10, choices=FREQUENCY_CHOICES)
    payee_type        = models.CharField(max_length=10, choices=PAYEE_TYPE_CHOICES, default='fixed')
    fixed_payee_phone = models.CharField(max_length=20, blank=True, null=True)
    is_active         = models.BooleanField(default=True)
    created_at        = models.DateTimeField(auto_now_add=True)
    # Schedule tracking — prevents the Celery task from firing every run
    next_run_at      = models.DateTimeField(null=True, blank=True, db_index=True)
    last_executed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.contribution.title} | KES {self.amount} | {self.frequency} | {self.payee_type}"


class StandingOrderSlot(models.Model):
    order        = models.ForeignKey(StandingOrder, on_delete=models.CASCADE, related_name='slots')
    phone_number = models.CharField(max_length=20)
    name         = models.CharField(max_length=120, blank=True, default='')
    slot_order   = models.PositiveIntegerField()
    has_received = models.BooleanField(default=False)
    received_at  = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['slot_order']
        unique_together = ['order', 'slot_order']

    def __str__(self):
        return f"Slot {self.slot_order} — {self.phone_number}"


# ---------------------------------------------------------------------------
# Multi-signature Disbursement Requests
# ---------------------------------------------------------------------------

class DisbursementRequest(models.Model):
    """
    State machine:
        PENDING  → APPROVED  → EXECUTED   (success: vote approved → funds dispatched)
                 ↘ REJECTED               (terminal — vote rejected)
                 ↘ CANCELLED              (terminal — requester withdrew before vote)
        EXECUTED → APPROVED               (B2C failure rollback — admin can re-trigger)

    All status changes must go through transition_to() — direct .status assignment
    on a saved instance will raise TransitionError from save().
    """

    STATUS_CHOICES = (
        ('PENDING',   'Pending'),
        ('APPROVED',  'Approved'),
        ('REJECTED',  'Rejected'),
        ('EXECUTED',  'Executed'),
        ('CANCELLED', 'Cancelled'),
    )

    VALID_TRANSITIONS = {
        'PENDING':   frozenset({'APPROVED', 'REJECTED', 'CANCELLED'}),
        'APPROVED':  frozenset({'EXECUTED'}),
        'EXECUTED':  frozenset({'APPROVED'}),   # B2C failure rollback only
        'REJECTED':  frozenset(),                # terminal
        'CANCELLED': frozenset(),                # terminal
    }

    contribution   = models.ForeignKey(Contribution, on_delete=models.CASCADE, related_name='disbursement_requests')
    requested_by   = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='disbursement_requests')
    amount         = models.DecimalField(max_digits=12, decimal_places=2)
    reason         = models.TextField()
    recipient_phone = models.CharField(max_length=20)
    status         = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    created_at     = models.DateTimeField(auto_now_add=True)
    executed_at    = models.DateTimeField(null=True, blank=True)

    @property
    def approve_count(self):
        return self.votes.filter(vote='APPROVE').count()

    @property
    def reject_count(self):
        return self.votes.filter(vote='REJECT').count()

    class Meta:
        indexes = [
            models.Index(fields=['contribution', '-created_at'], name='disburse_req_contrib_date_idx'),
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._committed_status: str = self.status
        self._in_transition: bool = False

    def save(self, *args, **kwargs):
        """Block direct .status = '...' assignments — use transition_to() instead."""
        if (
            self.pk
            and self.status != self._committed_status
            and not self._in_transition
        ):
            raise TransitionError(
                f"DisbursementRequest {self.pk}: direct status assignment is not allowed "
                f"({self._committed_status!r} → {self.status!r}). "
                "Use transition_to() instead."
            )
        super().save(*args, **kwargs)
        self._committed_status = self.status

    def transition_to(self, new_status: str, *, executed_at=None) -> None:
        """
        Atomically advance the request's status.

        Uses UPDATE WHERE status = <current> so concurrent voters
        cannot both successfully transition the same request.
        Raises TransitionError on invalid graph edge or concurrent conflict.
        """
        if new_status not in self.VALID_TRANSITIONS.get(self.status, frozenset()):
            raise TransitionError(
                f"DisbursementRequest {self.id}: invalid transition "
                f"{self.status!r} → {new_status!r}. "
                f"Allowed from {self.status!r}: "
                f"{sorted(self.VALID_TRANSITIONS.get(self.status, set()))}"
            )

        update_kwargs: dict = {'status': new_status}
        if executed_at is not None:
            update_kwargs['executed_at'] = executed_at

        rows = DisbursementRequest.objects.filter(
            pk=self.pk, status=self.status,
        ).update(**update_kwargs)

        if rows == 0:
            raise TransitionError(
                f"DisbursementRequest {self.id}: transition {self.status!r} → {new_status!r} "
                "lost concurrent race — another process already advanced this request."
            )

        self._in_transition = True
        self.status = new_status
        self._committed_status = new_status
        self._in_transition = False
        if executed_at is not None:
            self.executed_at = executed_at

    def __str__(self):
        return f"{self.contribution.title} | KES {self.amount} | {self.status}"


class DisbursementVote(models.Model):
    VOTE_CHOICES = (('APPROVE', 'Approve'), ('REJECT', 'Reject'))
    request  = models.ForeignKey(DisbursementRequest, on_delete=models.CASCADE, related_name='votes')
    voter    = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='disbursement_votes')
    vote     = models.CharField(max_length=10, choices=VOTE_CHOICES)
    voted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['request', 'voter']

    def __str__(self):
        return f"{self.voter.phone_number} | {self.vote} | {self.request}"


# ---------------------------------------------------------------------------
# Welfare Fund (optional, per contribution group or community)
# ---------------------------------------------------------------------------

class WelfareFund(models.Model):
    community    = models.ForeignKey(
        Community, on_delete=models.CASCADE,
        related_name='welfare_funds', null=True, blank=True,
    )
    name                 = models.CharField(max_length=255, default='Welfare Fund')
    balance              = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    monthly_contribution = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.community.name if self.community else '?'} — {self.name}"


class WelfareContribution(models.Model):
    fund       = models.ForeignKey(WelfareFund, on_delete=models.CASCADE, related_name='contributions')
    user       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    amount     = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.phone_number} | KES {self.amount} -> {self.fund}"


class WelfareClaim(models.Model):
    """
    A member's request for a welfare payout.

    State machine:
        PENDING → APPROVED → DISBURSED   (success path)
               ↘ REJECTED               (terminal — admin reject)
        APPROVED → PENDING              (B2C failure rollback — admin can re-trigger)

    All status changes must go through transition_to() — direct .status assignment
    on a saved instance will raise TransitionError from save().
    """

    STATUS_CHOICES = (
        ('PENDING',   'Pending'),
        ('APPROVED',  'Approved'),
        ('REJECTED',  'Rejected'),
        ('DISBURSED', 'Disbursed'),
    )

    VALID_TRANSITIONS = {
        'PENDING':   frozenset({'APPROVED', 'REJECTED'}),
        'APPROVED':  frozenset({'DISBURSED', 'PENDING'}),  # PENDING = B2C failure rollback
        'REJECTED':  frozenset(),                           # terminal
        'DISBURSED': frozenset(),                           # terminal
    }

    fund             = models.ForeignKey(WelfareFund, on_delete=models.CASCADE, related_name='claims')
    claimant         = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='welfare_claims')
    amount_requested = models.DecimalField(max_digits=12, decimal_places=2)
    reason           = models.TextField()
    status               = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    created_at           = models.DateTimeField(auto_now_add=True)
    approved_at          = models.DateTimeField(null=True, blank=True)
    disbursed_at         = models.DateTimeField(null=True, blank=True)
    b2c_conversation_id  = models.CharField(max_length=255, null=True, blank=True)
    mpesa_receipt        = models.CharField(max_length=50, null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['fund', '-created_at'], name='welfare_claim_fund_date_idx'),
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._committed_status: str = self.status
        self._in_transition: bool = False

    @property
    def approve_count(self):
        return self.votes.filter(vote='APPROVE').count()

    def __str__(self):
        return f"{self.claimant.phone_number} | KES {self.amount_requested} | {self.status}"

    def save(self, *args, **kwargs):
        """Block direct .status = '...' assignments — use transition_to() instead."""
        if (
            self.pk
            and self.status != self._committed_status
            and not self._in_transition
        ):
            raise TransitionError(
                f"WelfareClaim {self.pk}: direct status assignment is not allowed "
                f"({self._committed_status!r} → {self.status!r}). "
                "Use transition_to() instead."
            )
        super().save(*args, **kwargs)
        self._committed_status = self.status

    def transition_to(self, new_status: str, *,
                      approved_at=None,
                      disbursed_at=None,
                      mpesa_receipt=None) -> None:
        """
        Atomically advance the claim's status.

        Uses UPDATE WHERE status = <current> so concurrent admin clicks
        cannot both successfully transition the same claim.
        Raises TransitionError on invalid graph edge or concurrent conflict.
        """
        if new_status not in self.VALID_TRANSITIONS.get(self.status, frozenset()):
            raise TransitionError(
                f"WelfareClaim {self.id}: invalid transition "
                f"{self.status!r} → {new_status!r}. "
                f"Allowed from {self.status!r}: "
                f"{sorted(self.VALID_TRANSITIONS.get(self.status, set()))}"
            )

        update_kwargs: dict = {'status': new_status}
        if approved_at is not None:
            update_kwargs['approved_at'] = approved_at
        if disbursed_at is not None:
            update_kwargs['disbursed_at'] = disbursed_at
        if mpesa_receipt is not None:
            update_kwargs['mpesa_receipt'] = mpesa_receipt

        rows = WelfareClaim.objects.filter(
            pk=self.pk, status=self.status,
        ).update(**update_kwargs)

        if rows == 0:
            raise TransitionError(
                f"WelfareClaim {self.id}: transition {self.status!r} → {new_status!r} "
                "lost concurrent race — another process already advanced this claim."
            )

        self._in_transition = True
        self.status = new_status
        self._committed_status = new_status
        self._in_transition = False
        if approved_at is not None:
            self.approved_at = approved_at
        if disbursed_at is not None:
            self.disbursed_at = disbursed_at
        if mpesa_receipt is not None:
            self.mpesa_receipt = mpesa_receipt


class WelfareVote(models.Model):
    VOTE_CHOICES = (('APPROVE', 'Approve'), ('REJECT', 'Reject'))
    claim    = models.ForeignKey(WelfareClaim, on_delete=models.CASCADE, related_name='votes')
    voter    = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='welfare_votes')
    vote     = models.CharField(max_length=10, choices=VOTE_CHOICES)
    voted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['claim', 'voter']


# ---------------------------------------------------------------------------
# Emergency Advances
# ---------------------------------------------------------------------------

class EmergencyAdvance(models.Model):
    """
    State machine:
        PENDING  → DISBURSED   (approve_advance — approve + disburse in one step)
                 ↘ REJECTED    (terminal — admin reject)
        APPROVED → DISBURSED   (re-disburse after B2C failure rollback)
        DISBURSED → REPAID     (terminal — fully repaid)
                  ↘ APPROVED   (B2C failure rollback — admin can re-trigger disbursal)

    All status changes must go through transition_to() — direct .status assignment
    on a saved instance will raise TransitionError from save().
    """

    STATUS_CHOICES = (
        ('PENDING',   'Pending'),
        ('APPROVED',  'Approved'),
        ('REJECTED',  'Rejected'),
        ('DISBURSED', 'Disbursed'),
        ('REPAID',    'Repaid'),
    )

    VALID_TRANSITIONS = {
        'PENDING':   frozenset({'DISBURSED', 'REJECTED'}),
        'APPROVED':  frozenset({'DISBURSED'}),             # re-disburse after B2C rollback
        'DISBURSED': frozenset({'REPAID', 'APPROVED'}),    # APPROVED = B2C failure rollback
        'REJECTED':  frozenset(),                           # terminal
        'REPAID':    frozenset(),                           # terminal
    }

    contribution   = models.ForeignKey(Contribution, on_delete=models.CASCADE, related_name='advances')
    borrower       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='advances')
    amount         = models.DecimalField(max_digits=12, decimal_places=2)
    interest_rate  = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('10.00'))
    status         = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    amount_repaid  = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    repayment_due  = models.DateField(null=True, blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    @property
    def total_due(self):
        return self.amount * (1 + self.interest_rate / Decimal('100'))

    @property
    def balance_due(self):
        return max(self.total_due - self.amount_repaid, Decimal('0'))

    class Meta:
        indexes = [
            models.Index(fields=['contribution', '-created_at'], name='advance_contrib_date_idx'),
            models.Index(fields=['borrower', 'status'],          name='advance_borrower_status_idx'),
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._committed_status: str = self.status
        self._in_transition: bool = False

    def save(self, *args, **kwargs):
        """Block direct .status = '...' assignments — use transition_to() instead."""
        if (
            self.pk
            and self.status != self._committed_status
            and not self._in_transition
        ):
            raise TransitionError(
                f"EmergencyAdvance {self.pk}: direct status assignment is not allowed "
                f"({self._committed_status!r} → {self.status!r}). "
                "Use transition_to() instead."
            )
        super().save(*args, **kwargs)
        self._committed_status = self.status

    def transition_to(self, new_status: str) -> None:
        """
        Atomically advance the advance's status.

        Uses UPDATE WHERE status = <current> so concurrent admin clicks
        cannot both successfully transition the same advance.
        Raises TransitionError on invalid graph edge or concurrent conflict.
        """
        if new_status not in self.VALID_TRANSITIONS.get(self.status, frozenset()):
            raise TransitionError(
                f"EmergencyAdvance {self.id}: invalid transition "
                f"{self.status!r} → {new_status!r}. "
                f"Allowed from {self.status!r}: "
                f"{sorted(self.VALID_TRANSITIONS.get(self.status, set()))}"
            )

        rows = EmergencyAdvance.objects.filter(
            pk=self.pk, status=self.status,
        ).update(status=new_status)

        if rows == 0:
            raise TransitionError(
                f"EmergencyAdvance {self.id}: transition {self.status!r} → {new_status!r} "
                "lost concurrent race — another process already advanced this advance."
            )

        self._in_transition = True
        self.status = new_status
        self._committed_status = new_status
        self._in_transition = False

    def __str__(self):
        return f"{self.borrower.phone_number} | KES {self.amount} | {self.status}"


# ---------------------------------------------------------------------------
# Contribution Amendments (sensitive field changes requiring group vote)
# ---------------------------------------------------------------------------

class ContributionAmendment(models.Model):
    """
    A proposal to change one or more sensitive fields on a Contribution.
    Goes through the contribution's own voting_threshold before being applied.

    Sensitive fields: fixed_amount, target_amount, voting_threshold,
                      end_date, period_months, visibility.
    """
    STATUS_CHOICES = (
        ('PENDING',   'Pending'),
        ('APPROVED',  'Approved'),
        ('REJECTED',  'Rejected'),
        ('WITHDRAWN', 'Withdrawn'),
    )

    contribution = models.ForeignKey(
        Contribution, on_delete=models.CASCADE, related_name='amendments'
    )
    proposed_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='proposed_amendments'
    )
    # JSON snapshot of proposed changes e.g. {"fixed_amount": "1500.00", "voting_threshold": "50"}
    changes      = models.JSONField()
    reason       = models.TextField(blank=True)
    status       = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    created_at   = models.DateTimeField(auto_now_add=True)
    resolved_at  = models.DateTimeField(null=True, blank=True)

    @property
    def approve_count(self):
        return self.votes.filter(vote='APPROVE').count()

    @property
    def reject_count(self):
        return self.votes.filter(vote='REJECT').count()

    def __str__(self):
        return f"Amendment #{self.id} on '{self.contribution.title}' [{self.status}]"


class ContributionAmendmentVote(models.Model):
    VOTE_CHOICES = (('APPROVE', 'Approve'), ('REJECT', 'Reject'))
    amendment = models.ForeignKey(ContributionAmendment, on_delete=models.CASCADE, related_name='votes')
    voter     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='amendment_votes')
    vote      = models.CharField(max_length=10, choices=VOTE_CHOICES)
    voted_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['amendment', 'voter']


class ContributionJoinRequest(models.Model):
    """
    Handles both member-initiated join requests and admin-initiated invitations
    for a contribution. A single row per (contribution, user) pair.
    """
    TYPE_CHOICES = (
        ('REQUEST', 'Join Request'),   # member asked to join
        ('INVITE',  'Invitation'),     # admin/creator invited a member
    )
    STATUS_CHOICES = (
        ('PENDING',   'Pending'),
        ('APPROVED',  'Approved'),
        ('REJECTED',  'Rejected'),
    )

    contribution  = models.ForeignKey(Contribution, on_delete=models.CASCADE, related_name='join_requests')
    user          = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='contribution_join_requests')
    request_type  = models.CharField(max_length=10, choices=TYPE_CHOICES)
    invited_by    = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='contribution_invitations_sent',
    )
    status        = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    created_at    = models.DateTimeField(auto_now_add=True)
    reviewed_at   = models.DateTimeField(null=True, blank=True)
    reviewed_by   = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='contribution_requests_reviewed',
    )

    class Meta:
        unique_together = ('contribution', 'user')

    def __str__(self):
        return f"{self.request_type} — {self.user.phone_number} → {self.contribution.title} [{self.status}]"
