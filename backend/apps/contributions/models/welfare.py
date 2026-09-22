"""Welfare funds, member contributions into them, and claims against them."""

from django.conf import settings
from django.db import models

from apps.communities.models import Community
from apps.core.exceptions import TransitionError


class WelfareFund(models.Model):
    # Program spine (ADR-0026): this fund is the archetype profile of a Program.
    # Stamped at creation, backfilled for pre-spine rows (hence nullable).
    program = models.OneToOneField(
        'organizations.Program', null=True, blank=True,
        on_delete=models.PROTECT, related_name='welfare_profile',
    )

    community    = models.ForeignKey(
        Community, on_delete=models.PROTECT,
        related_name='welfare_funds', null=True, blank=True,
    )
    name                 = models.CharField(max_length=255, default='Welfare Fund')
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
