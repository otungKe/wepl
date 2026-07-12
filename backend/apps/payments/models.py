from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.exceptions import TransitionError


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

    Boundary (ADR-0014, item 10): this is provider-lifecycle state ONLY. It never
    references a business object (Contribution/Loan/Welfare/Shares/Advance) — it
    links to the ledger ``FinancialTransaction`` and carries a denormalised
    ``op_type`` *label* for analytics, nothing more. It must not grow into a
    business aggregate.
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

    # Provider-side completion is reached at SUCCEEDED/FAILED (REVERSED is a later
    # internal refund, not a provider event).
    _PROVIDER_TERMINAL = frozenset({Status.SUCCEEDED, Status.FAILED})

    provider     = models.CharField(max_length=30, db_index=True)   # 'mpesa', 'fake', …
    # `direction` is the PROVIDER-lifecycle axis: is money flowing in (collection)
    # or out (payout)? It is intrinsic to the rail interaction. Distinct from
    # `op_type` below (the originating *business* operation) — the two are not
    # duplicates: one intent direction (payout) serves many op_types (disbursement,
    # ROSCA payout, welfare claim, advance…).
    direction    = models.CharField(
        max_length=12, choices=Direction.choices,
        help_text="Provider money-flow axis (pay-in vs pay-out); not the business op — see op_type.")
    status       = models.CharField(max_length=12, choices=Status.choices,
                                    default=Status.PENDING, db_index=True)

    amount       = models.DecimalField(max_digits=14, decimal_places=2)
    # Kenya-only for now (item 8): fixed to KES and not operator-editable. When
    # multi-currency lands, drop editable=False and thread a currency through.
    currency     = models.CharField(max_length=3, default='KES', editable=False)

    # Provider correlation id (CheckoutRequestID / ConversationID). Indexed for
    # callback resolution and unique-per-provider once populated (see Meta).
    provider_ref = models.CharField(max_length=255, blank=True, default='', db_index=True)
    receipt      = models.CharField(max_length=64, blank=True, default='')

    # Idempotency for initiation (safe under retried initiates).
    idempotency_key = models.CharField(max_length=128, unique=True)

    # Link to the internal money-op (set for payouts at initiate; collections link
    # later via the STK request → contribution path). This FK to the ledger is the
    # ONLY cross-aggregate reference — no business-object FKs live here.
    financial_transaction = models.ForeignKey(
        'ledger.FinancialTransaction', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='payment_intents',
    )
    # Denormalised *label* of the originating business operation (CONTRIBUTION,
    # DISBURSEMENT…), copied from the FinancialTransaction for provider analytics
    # and debugging. A free string, never an FK — it creates no dependency on any
    # business app and is not authoritative (the ledger is).
    op_type      = models.CharField(
        max_length=30, blank=True, default='',
        help_text="Denormalised business-op label for analytics; not a dependency, not authoritative.")

    tenant       = models.ForeignKey('tenants.Tenant', null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name='payment_intents')
    initiated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name='payment_intents')

    # Structured failure info (item 5) — a machine-usable code + a human message,
    # so failures can be classified (retryable vs terminal), charted per provider,
    # and diagnosed. Replaces the old free-text `failure_reason`.
    failure_code    = models.CharField(
        max_length=64, blank=True, default='',
        help_text="Provider/normalised failure code for analytics & retry classification.")
    failure_message = models.TextField(blank=True, default='')
    metadata        = models.JSONField(default=dict, blank=True)

    # Provider lifecycle timestamps (item 3) — dedicated to reconciliation, SLA
    # monitoring, timeout detection, and dispute investigation. Distinct from the
    # generic created_at/updated_at (row bookkeeping).
    initiated_at          = models.DateTimeField(null=True, blank=True,
                                                 help_text="When the provider accepted initiation.")
    callback_received_at  = models.DateTimeField(null=True, blank=True,
                                                 help_text="When the settling provider callback landed.")
    provider_completed_at = models.DateTimeField(null=True, blank=True,
                                                 help_text="When the provider reached a terminal result.")

    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            # Retained lookup index for callback resolution (provider_ref lookups).
            models.Index(fields=['provider', 'provider_ref'], name='pi_provider_ref_idx'),
            models.Index(fields=['status', 'created_at'],      name='pi_status_created_idx'),
        ]
        constraints = [
            # A provider correlation id identifies at most one payment within a
            # provider — once populated. Blank refs are allowed during initiation.
            models.UniqueConstraint(
                fields=['provider', 'provider_ref'],
                condition=~Q(provider_ref=''),
                name='uniq_provider_ref_per_provider'),
            # A provider receipt (e.g. M-Pesa receipt) never exists twice — once
            # populated. Blank receipts are allowed until settlement.
            models.UniqueConstraint(
                fields=['receipt'],
                condition=~Q(receipt=''),
                name='uniq_provider_receipt'),
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Shadow the loaded status so save() can reject direct reassignment.
        self._committed_status = self.status
        self._in_transition = False

    def __str__(self):
        return f"PaymentIntent[{self.provider}/{self.direction}] {self.amount} {self.status}"

    def save(self, *args, **kwargs):
        """Block ad-hoc ``.status = …`` on an existing row — all status changes go
        through transition_to() so the state machine and its side effects (item 4)
        are never bypassed."""
        if (self.pk
                and self.status != self._committed_status
                and not self._in_transition):
            raise TransitionError(
                f"PaymentIntent {self.pk}: direct status assignment is not allowed "
                f"({self._committed_status!r} → {self.status!r}). Use transition_to().")
        super().save(*args, **kwargs)
        self._committed_status = self.status

    def transition_to(self, target, *, receipt='', failure_code='', failure_message='',
                      metadata=None, completed_at=None):
        """The single, guarded door for status changes (item 4).

        Validates against VALID_TRANSITIONS, applies the change under an optimistic
        ``UPDATE WHERE status=<current>`` lock (so concurrent callbacks can't both
        settle), stamps the lifecycle timestamp, and folds in receipt / structured
        failure / metadata. Raises TransitionError on an illegal edge or a lost
        race — callers that want best-effort semantics catch it.
        """
        if target not in self.VALID_TRANSITIONS.get(self.status, frozenset()):
            raise TransitionError(
                f"PaymentIntent {self.pk}: illegal transition {self.status!r} → {target!r}.")

        now = timezone.now()
        updates = {'status': target, 'updated_at': now}
        if receipt:
            updates['receipt'] = receipt[:64]
        if failure_code:
            updates['failure_code'] = failure_code[:64]
        if failure_message:
            updates['failure_message'] = failure_message
        if metadata:
            updates['metadata'] = {**(self.metadata or {}), **metadata}
        if target in self._PROVIDER_TERMINAL:
            updates['provider_completed_at'] = completed_at or now

        rows = PaymentIntent.objects.filter(pk=self.pk, status=self.status).update(**updates)
        if rows == 0:
            raise TransitionError(
                f"PaymentIntent {self.pk}: transition {self.status!r} → {target!r} lost a "
                "concurrent race — another worker already advanced it.")

        # Reflect the committed change in memory without tripping the save guard.
        self._in_transition = True
        for field, value in updates.items():
            setattr(self, field, value)
        self._committed_status = target
        self._in_transition = False
        return self


class ProviderEvent(models.Model):
    """Append-only history of raw provider callbacks/events (ADR-0014, item 6).

    Preserves the exact payload the rail delivered so we can audit, investigate
    disputes, reconcile against, and replay provider events. Never mutated —
    corrections are new rows (like the ledger's journals). Deliberately decoupled
    from business objects: it references only the PaymentIntent (nullable, since an
    event may arrive before an intent is linked) and raw provider identifiers.

    Callback history lives HERE, never inside PaymentIntent.
    """
    payment_intent = models.ForeignKey(
        PaymentIntent, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='provider_events')
    provider       = models.CharField(max_length=30, db_index=True)
    provider_ref   = models.CharField(max_length=255, blank=True, default='', db_index=True)
    event_type     = models.CharField(
        max_length=40, help_text="e.g. collection_callback, payout_result, c2b_confirmation.")
    payload        = models.JSONField(default=dict, blank=True)
    signature_verified = models.BooleanField(
        default=False, help_text="Did the event pass the provider's authenticity check (IP/HMAC)?")
    provider_event_id  = models.CharField(
        max_length=128, blank=True, default='',
        help_text="The provider's own event id, when it supplies one (for dedup/replay).")
    received_at    = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-received_at']
        indexes = [
            models.Index(fields=['provider', 'provider_ref'],       name='pe_provider_ref_idx'),
            models.Index(fields=['payment_intent', 'received_at'],  name='pe_intent_received_idx'),
        ]
        constraints = [
            # Dedup a re-delivered event when the rail carries its own id.
            models.UniqueConstraint(
                fields=['provider', 'provider_event_id'],
                condition=~Q(provider_event_id=''),
                name='uniq_provider_event_id'),
        ]

    def __str__(self):
        return f"ProviderEvent[{self.provider}/{self.event_type}] {self.provider_ref}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise TransitionError("ProviderEvent is append-only — write a new row, never edit.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise TransitionError("ProviderEvent is append-only — it cannot be deleted.")


class ReconciliationDrift(models.Model):
    """A discrepancy found by the payments reconciliation pass (ADR-0014).

    Append-only audit of where the provider/intent/ledger views disagree, for
    ops triage. ``resolve()`` is the only mutation.
    """
    KIND_CHOICES = (
        # Detected today.
        ('stuck_pending_intent', 'Stuck pending intent'),
        ('intent_ft_mismatch',   'Intent/FinancialTransaction state mismatch'),
        ('ft_without_journal',    'Successful FT without a posted journal'),
        ('ft_stuck_processing',   'FinancialTransaction stuck in processing'),
        ('amount_mismatch',       'Intent/FinancialTransaction amount mismatch'),
        ('duplicate_receipt',     'Provider receipt seen on more than one intent'),
        # Vocabulary for detectors added over time (item 9).
        ('duplicate_callback',              'Duplicate provider callback'),
        ('provider_timeout',                'Provider timed out with no result'),
        ('missing_callback',                'Initiated payment with no callback'),
        ('provider_success_ledger_failure', 'Provider succeeded but ledger did not'),
        ('ledger_success_provider_failure', 'Ledger succeeded but provider did not'),
        ('orphan_provider_txn',             'Provider transaction with no intent'),
        ('late_callback',                   'Callback arrived after the grace window'),
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
