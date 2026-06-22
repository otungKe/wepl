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

