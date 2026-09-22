"""Emergency advances — the one place a member owes the pool money."""

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils.functional import cached_property

from apps.core.exceptions import TransitionError

from .contribution import Contribution


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
    repayment_due  = models.DateField(null=True, blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    @cached_property
    def amount_repaid(self):
        """Cash received against this advance, read from its repayment journals.

        This was a mutable column incremented in ``repay()`` alongside — but
        separately from — the journal that repayment posted, which is how it came
        to double-count a replayed settlement callback. Deriving it means a
        replay cannot move it at all: ``post_journal`` refuses the duplicate, and
        there is no second write left to get wrong.

        Cached per instance because ``balance_due`` is expressed in terms of it.
        An instance that spans a repayment should be re-fetched rather than read
        again; ``advance_repaid_totals`` reads many advances in one query.
        """
        from apps.ledger.balances import advance_repaid
        return advance_repaid(self.id)

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
