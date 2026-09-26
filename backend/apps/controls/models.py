"""
Controls layer — limits & risk (Phase 3, ADR-0007).

Two models:
  • LimitRule        — config-driven caps (amount/count) per scope/op_type/
                       direction/period, with an action (DENY or HOLD).
  • ControlDecision  — append-only audit of every evaluation at the posting
                       chokepoint (allow / deny / hold + reason + window totals).

The ledger stays pure accounting; all control policy lives here. The engine
(engine.py) is invoked by post_journal() so enforcement happens in exactly one
place and cannot be bypassed by using a different code path.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.ledger.models import FinancialTransaction


class LimitRule(models.Model):
    class Scope(models.TextChoices):
        GLOBAL   = 'GLOBAL',   'Global (platform-wide)'
        PER_USER = 'PER_USER', 'Per user'

    class Direction(models.TextChoices):
        ANY    = 'ANY',    'Any'
        PAYIN  = 'PAYIN',  'Pay-in'
        PAYOUT = 'PAYOUT', 'Pay-out'

    class Period(models.TextChoices):
        TXN   = 'TXN',   'Per transaction'
        HOUR  = 'HOUR',  'Rolling hour'
        DAY   = 'DAY',   'Calendar day'
        WEEK  = 'WEEK',  'Calendar week'
        MONTH = 'MONTH', 'Calendar month'

    class Action(models.TextChoices):
        DENY = 'DENY', 'Deny'
        HOLD = 'HOLD', 'Hold for review'

    name      = models.CharField(max_length=120)
    # Null = global rule (all tenants); set = applies only to that tenant (P6-03).
    tenant    = models.ForeignKey(
        'tenants.Tenant', null=True, blank=True,
        on_delete=models.CASCADE, related_name='limit_rules',
    )
    scope     = models.CharField(max_length=10, choices=Scope.choices, default=Scope.PER_USER)
    direction = models.CharField(max_length=6, choices=Direction.choices, default=Direction.PAYOUT)
    # Blank = applies to all op_types in the direction.
    op_type   = models.CharField(max_length=30, choices=FinancialTransaction.OpType.choices, blank=True)
    period    = models.CharField(max_length=5, choices=Period.choices, default=Period.DAY)
    max_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    max_count  = models.PositiveIntegerField(null=True, blank=True)
    action    = models.CharField(max_length=4, choices=Action.choices, default=Action.DENY)
    priority  = models.PositiveIntegerField(default=100, help_text='Lower runs first; DENY short-circuits.')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('priority', 'id')

    def __str__(self):
        cap = f"{self.max_amount}" if self.max_amount is not None else f"{self.max_count}×"
        return f"{self.name} [{self.scope}/{self.direction}/{self.period} {cap} → {self.action}]"


class ControlDecision(models.Model):
    """Append-only audit row written for every control evaluation."""

    class Outcome(models.TextChoices):
        ALLOW = 'ALLOW', 'Allow'
        DENY  = 'DENY',  'Deny'
        HOLD  = 'HOLD',  'Hold'

    created_at  = models.DateTimeField(auto_now_add=True, db_index=True)
    decision    = models.CharField(max_length=5, choices=Outcome.choices)
    op_type     = models.CharField(max_length=30)
    direction   = models.CharField(max_length=6)
    amount      = models.DecimalField(max_digits=14, decimal_places=2)
    subject_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='control_decisions',
    )
    financial_transaction = models.ForeignKey(
        FinancialTransaction, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='control_decisions',
    )
    rule = models.ForeignKey(
        LimitRule, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='decisions',
    )
    reason       = models.TextField(blank=True)
    window_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    window_count  = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ('-created_at',)
        indexes = [
            models.Index(fields=['decision', 'created_at'], name='ctrl_decision_idx'),
            models.Index(fields=['subject_user', 'created_at'], name='ctrl_subject_idx'),
        ]

    def __str__(self):
        return f"{self.decision} {self.op_type} {self.amount} ({self.created_at:%Y-%m-%d %H:%M})"


class HeldMovement(models.Model):
    """Durable manual-review queue for blocked movements (P3-04).

    A held (HOLD) or denied (DENY) movement leaves no FinancialTransaction behind
    — the service's atomic block rolls back when the control exception propagates.
    This row is written by the DRF exception handler *after* that rollback, so it
    persists and is reviewable. It captures enough context (idempotency_key, fund,
    parties) for an operator to understand and act on the blocked movement.
    """

    class Decision(models.TextChoices):
        DENY = 'DENY', 'Denied'
        HOLD = 'HOLD', 'Held'

    class Status(models.TextChoices):
        OPEN     = 'OPEN',     'Open'
        RELEASED = 'RELEASED', 'Released'
        REJECTED = 'REJECTED', 'Rejected'

    created_at   = models.DateTimeField(auto_now_add=True, db_index=True)
    decision     = models.CharField(max_length=5, choices=Decision.choices)
    status       = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    op_type      = models.CharField(max_length=30)
    direction    = models.CharField(max_length=6)
    amount       = models.DecimalField(max_digits=14, decimal_places=2)
    subject_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='held_movements',
    )
    recipient_phone = models.CharField(max_length=20, blank=True)
    idempotency_key = models.CharField(max_length=128, blank=True, db_index=True)
    context_type = models.CharField(max_length=30, blank=True)
    context_id   = models.PositiveIntegerField(null=True, blank=True)
    rule = models.ForeignKey(
        LimitRule, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='held_movements',
    )
    reason       = models.TextField(blank=True)

    # Review trail
    reviewed_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='reviewed_held_movements',
    )
    reviewed_at  = models.DateTimeField(null=True, blank=True)
    review_note  = models.TextField(blank=True)

    class Meta:
        ordering = ('-created_at',)
        indexes = [
            models.Index(fields=['status', 'created_at'], name='held_status_idx'),
        ]

    def __str__(self):
        return f"[{self.status}] {self.decision} {self.op_type} {self.amount}"



class ControlOverride(models.Model):
    """A single-use, time-boxed pre-clearance for a HOLD-class limit.

    Issued when compliance approves an EDD case over a held movement (the
    customer provided supporting documents), so their retry of that specific
    movement passes the HOLD rule instead of being re-held. Overrides never
    bypass DENY rules — hard caps stay hard.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='control_overrides',
    )
    # Blank = any op type; normally copied from the held movement.
    op_type    = models.CharField(max_length=30, blank=True)
    max_amount = models.DecimalField(max_digits=14, decimal_places=2)

    expires_at  = models.DateTimeField(db_index=True)
    consumed_at = models.DateTimeField(null=True, blank=True)

    # Provenance (loose references — no cross-app FK coupling to verification).
    source_case     = models.CharField(max_length=64, blank=True, default='')
    held_movement   = models.ForeignKey(
        HeldMovement, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='overrides',
    )
    issued_by_label = models.CharField(max_length=120, blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)
        indexes = [
            models.Index(fields=['user', 'expires_at'], name='override_user_expiry_idx'),
        ]

    def __str__(self):
        state = 'consumed' if self.consumed_at else 'active'
        return f"Override({self.user_id}, {self.op_type or 'any'}, <={self.max_amount}, {state})"


class UserRestriction(models.Model):
    """An account-level restriction placed on a customer by back-office staff.

    A restriction narrows what a customer may do WITHOUT closing the account
    (full closure stays ``UserService.deactivate_user``) and WITHOUT ever
    deleting them. Each kind maps to a real enforcement chokepoint:

      * ``LOGIN``  → the authentication path (PIN login) rejects the sign-in.
      * money kinds → the ledger control chokepoint (``enforce_controls``) hard-
        DENYs the movement, so no money path can bypass it.

    There is no "wallet" to freeze (ADR-0002: balances are ledger projections);
    ``FREEZE`` blocks *all* money movement for the member instead.

    Append-only history: a restriction is never edited once applied — lifting
    sets ``status=LIFTED`` with who/when/why; a past-expiry restriction reads as
    inactive and is swept to ``EXPIRED`` by a beat task. At most one ACTIVE
    restriction of a given kind may exist per user (DB-enforced).
    """

    class Kind(models.TextChoices):
        LOGIN            = "login",            "Suspend login"
        PAYOUT           = "payout",           "Block money out (withdrawals / transfers)"
        PAYIN            = "payin",            "Block money in (deposits)"
        FREEZE           = "freeze",           "Freeze all money movement"
        COMMUNITY_CREATE = "community_create", "Restrict community creation"
        COMMUNITY_ADMIN  = "community_admin",  "Restrict community administration"

    class Status(models.TextChoices):
        ACTIVE  = "active",  "Active"
        LIFTED  = "lifted",  "Lifted"
        EXPIRED = "expired", "Expired"

    user   = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                               related_name="restrictions")
    kind   = models.CharField(max_length=20, choices=Kind.choices)
    status = models.CharField(max_length=10, choices=Status.choices,
                              default=Status.ACTIVE, db_index=True)
    reason = models.TextField()

    effective_at = models.DateTimeField(default=timezone.now)
    expires_at   = models.DateTimeField(null=True, blank=True)  # null = indefinite

    applied_by_label = models.CharField(max_length=120, blank=True, default="")
    approval_ref     = models.CharField(max_length=64, blank=True, default="")

    lifted_at       = models.DateTimeField(null=True, blank=True)
    lifted_by_label = models.CharField(max_length=120, blank=True, default="")
    lift_reason     = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Owned by controls since the boundary audit (step 7); the table kept
        # its original name, so the move changed no data.
        db_table = "users_userrestriction"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["user", "status"], name="restriction_user_status_idx"),
            models.Index(fields=["kind", "status"], name="restriction_kind_status_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "kind"], condition=models.Q(status="active"),
                name="uniq_active_restriction_per_kind"),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} on user {self.user_id} [{self.status}]"

    @property
    def is_effective(self) -> bool:
        """Currently in force: ACTIVE, started, and not past expiry."""
        now = timezone.now()
        return (self.status == self.Status.ACTIVE
                and self.effective_at <= now
                and (self.expires_at is None or self.expires_at > now))
