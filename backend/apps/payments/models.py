from django.conf import settings
from django.db import models

from apps.contributions.models import Contribution


class Payment(models.Model):

    # -----------------------------
    # PAYMENT STATUS TRACKING
    # Important for M-Pesa + future gateways
    # -----------------------------
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),     # initiated but not confirmed
        ('COMPLETED', 'Completed'), # successful payment
        ('FAILED', 'Failed'),       # failed transaction
        ('REVERSED', 'Reversed'),   # refunded/reversed
    )

    # -----------------------------
    # LINK TO CONTRIBUTION (SACCO POOL)
    # -----------------------------
    contribution = models.ForeignKey(
        Contribution,
        on_delete=models.CASCADE,
        related_name='payments'
    )

    # -----------------------------
    # USER WHO MADE THE PAYMENT
    # (ALWAYS phone_number-based system)
    # -----------------------------
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='payments'
    )

    # -----------------------------
    # PAYMENT AMOUNT
    # -----------------------------
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    # -----------------------------
    # EXTERNAL REFERENCE (M-PESA / CASH REF)
    # -----------------------------
    reference = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    # -----------------------------
    # PAYMENT STATUS
    # -----------------------------
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='COMPLETED'
    )

    # -----------------------------
    # WHO RECORDED THE PAYMENT
    # (admin, system, or self-recorded)
    # -----------------------------
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='recorded_payments'
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['contribution', '-created_at'], name='payment_contrib_date_idx'),
            models.Index(fields=['user',         '-created_at'], name='payment_user_date_idx'),
        ]

    def __str__(self):
        # Mobile-friendly identity display
        return f"{self.user.phone_number} - {self.amount}"

# ===========================================================================
# Provider-agnostic payment aggregate (ADR-0014)
# ===========================================================================

class PaymentIntent(models.Model):
    """A single attempt to move money through *a* provider, independent of the
    rail's wire details.

    The ledger ``FinancialTransaction`` remains the internal money-op + journal
    anchor; this aggregate captures the *external* payment lifecycle
    (initiated → settled/failed/reversed) keyed by the provider's correlation id,
    so a second provider (card/bank) slots in without callers changing. It is fed
    at the provider chokepoints (collection/payout × initiate/callback).
    """

    class Direction(models.TextChoices):
        COLLECTION = 'collection', 'Collection (pay-in)'
        PAYOUT     = 'payout',     'Payout (pay-out)'

    class Status(models.TextChoices):
        PENDING   = 'pending',   'Pending'      # initiated, awaiting provider callback
        SUCCEEDED = 'succeeded', 'Succeeded'
        FAILED    = 'failed',    'Failed'
        REVERSED  = 'reversed',  'Reversed'

    VALID_TRANSITIONS = {
        Status.PENDING:   frozenset({Status.SUCCEEDED, Status.FAILED}),
        Status.SUCCEEDED: frozenset({Status.REVERSED}),
        Status.FAILED:    frozenset(),
        Status.REVERSED:  frozenset(),
    }

    provider     = models.CharField(max_length=30, db_index=True)   # 'mpesa', 'fake', …
    direction    = models.CharField(max_length=12, choices=Direction.choices)
    status       = models.CharField(max_length=12, choices=Status.choices,
                                    default=Status.PENDING, db_index=True)

    amount       = models.DecimalField(max_digits=14, decimal_places=2)
    currency     = models.CharField(max_length=3, default='KES')

    # Provider correlation id (CheckoutRequestID / ConversationID). Indexed for
    # callback resolution; not globally unique across providers.
    provider_ref = models.CharField(max_length=255, blank=True, default='', db_index=True)
    receipt      = models.CharField(max_length=64, blank=True, default='')

    # Idempotency for initiation (safe under retried initiates).
    idempotency_key = models.CharField(max_length=128, unique=True)

    # Link to the internal money-op (set for payouts at initiate; collections link
    # later via the STK request → contribution path).
    financial_transaction = models.ForeignKey(
        'ledger.FinancialTransaction', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='payment_intents',
    )
    op_type      = models.CharField(max_length=30, blank=True, default='')

    tenant       = models.ForeignKey('tenants.Tenant', null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name='payment_intents')
    initiated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name='payment_intents')

    failure_reason = models.TextField(blank=True, default='')
    metadata       = models.JSONField(default=dict, blank=True)

    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['provider', 'provider_ref'], name='pi_provider_ref_idx'),
            models.Index(fields=['status', 'created_at'],      name='pi_status_created_idx'),
        ]

    def __str__(self):
        return f"PaymentIntent[{self.provider}/{self.direction}] {self.amount} {self.status}"


class ReconciliationDrift(models.Model):
    """A discrepancy found by the payments reconciliation pass (ADR-0014).

    Append-only audit of where the provider/intent/ledger views disagree, for
    ops triage. ``resolve()`` is the only mutation.
    """
    KIND_CHOICES = (
        ('stuck_pending_intent', 'Stuck pending intent'),
        ('intent_ft_mismatch',   'Intent/FinancialTransaction state mismatch'),
        ('ft_without_journal',    'Successful FT without a posted journal'),
        ('ft_stuck_processing',   'FinancialTransaction stuck in processing'),
    )

    kind         = models.CharField(max_length=40, choices=KIND_CHOICES, db_index=True)
    subject_type = models.CharField(max_length=30)   # 'payment_intent' | 'financial_transaction'
    subject_id   = models.CharField(max_length=64)
    detail       = models.TextField(blank=True, default='')
    detected_at  = models.DateTimeField(auto_now_add=True, db_index=True)
    resolved_at  = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-detected_at']
        indexes = [
            models.Index(fields=['kind', 'resolved_at'], name='drift_kind_resolved_idx'),
        ]
        constraints = [
            # One open drift per (kind, subject) — re-runs don't pile up duplicates.
            models.UniqueConstraint(
                fields=['kind', 'subject_type', 'subject_id'],
                condition=models.Q(resolved_at__isnull=True),
                name='uniq_open_drift_per_subject',
            ),
        ]

    def __str__(self):
        state = 'resolved' if self.resolved_at else 'open'
        return f"Drift[{self.kind}] {self.subject_type}#{self.subject_id} ({state})"
