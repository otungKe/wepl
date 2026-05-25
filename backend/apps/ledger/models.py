"""
Financial ledger — the single source of truth for all money movements.

FinancialTransaction  — one complete financial event with a strict state machine.
LedgerEntry           — immutable, append-only credit/debit record.

Balances are ALWAYS derived:  SUM(CREDIT entries) - SUM(DEBIT entries)
Mutable balance fields on other models exist only as a performance cache
and will be removed once the ledger is the confirmed primary read source.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.exceptions import TransitionError


class FinancialTransaction(models.Model):
    """
    One complete financial event.  Moves through a strict one-way state machine:

        PENDING → PROCESSING → SUCCESS
                            ↘ FAILED   (terminal)
        SUCCESS → REVERSED             (terminal)

    State transitions are performed by transition_to(), which uses
    UPDATE WHERE state = <expected> to prevent concurrent double-transitions.
    """

    class State(models.TextChoices):
        PENDING    = 'PENDING',    'Pending'
        PROCESSING = 'PROCESSING', 'Processing'
        SUCCESS    = 'SUCCESS',    'Success'
        FAILED     = 'FAILED',     'Failed'
        REVERSED   = 'REVERSED',   'Reversed'

    class OpType(models.TextChoices):
        CONTRIBUTION         = 'CONTRIBUTION',         'Member Contribution'
        DISBURSEMENT         = 'DISBURSEMENT',         'Disbursement'
        STANDING_ORDER       = 'STANDING_ORDER',       'Standing Order Payout'
        ROSCA_PAYOUT         = 'ROSCA_PAYOUT',         'ROSCA Payout'
        ADVANCE_DISBURSEMENT = 'ADVANCE_DISBURSEMENT', 'Emergency Advance Disbursement'
        ADVANCE_REPAYMENT    = 'ADVANCE_REPAYMENT',    'Emergency Advance Repayment'
        WELFARE_CONTRIBUTION = 'WELFARE_CONTRIBUTION', 'Welfare Contribution'
        WELFARE_CLAIM        = 'WELFARE_CLAIM',        'Welfare Claim Disbursement'
        SHARES_PURCHASE      = 'SHARES_PURCHASE',      'Shares Purchase'

    VALID_TRANSITIONS = {
        State.PENDING:    frozenset({State.PROCESSING, State.FAILED}),
        State.PROCESSING: frozenset({State.SUCCESS,    State.FAILED}),
        State.SUCCESS:    frozenset({State.REVERSED}),
        State.FAILED:     frozenset(),
        State.REVERSED:   frozenset(),
    }

    # ── Core ──────────────────────────────────────────────────────────────────
    op_type         = models.CharField(max_length=30, choices=OpType.choices)
    state           = models.CharField(max_length=20, choices=State.choices,
                                       default=State.PENDING)
    amount          = models.DecimalField(max_digits=14, decimal_places=2)
    idempotency_key = models.CharField(max_length=128, unique=True, db_index=True)

    # ── Context — which fund this belongs to ──────────────────────────────────
    contribution = models.ForeignKey(
        'contributions.Contribution', null=True, blank=True,
        on_delete=models.PROTECT, related_name='fin_transactions',
    )
    welfare_fund = models.ForeignKey(
        'contributions.WelfareFund', null=True, blank=True,
        on_delete=models.PROTECT, related_name='fin_transactions',
    )
    shares_fund = models.ForeignKey(
        'contributions.SharesFund', null=True, blank=True,
        on_delete=models.PROTECT, related_name='fin_transactions',
    )

    # ── Context — which domain object triggered this ───────────────────────────
    # Stored as plain IDs to avoid circular FK imports.
    # 'disbursement_request' | 'welfare_claim' | 'emergency_advance' | 'standing_order'
    context_type = models.CharField(max_length=30, blank=True)
    context_id   = models.PositiveIntegerField(null=True, blank=True)

    # ── Parties ───────────────────────────────────────────────────────────────
    initiated_by    = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='initiated_fin_txs',
    )
    recipient_phone = models.CharField(max_length=20, blank=True)

    # ── External payment tracking ──────────────────────────────────────────────
    mpesa_checkout_id     = models.CharField(max_length=255, null=True, blank=True, unique=True)
    mpesa_conversation_id = models.CharField(max_length=255, null=True, blank=True, unique=True)
    mpesa_receipt         = models.CharField(max_length=50,  null=True, blank=True, unique=True)

    # ── Metadata ──────────────────────────────────────────────────────────────
    note           = models.TextField(blank=True)
    failure_reason = models.TextField(blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['state', 'op_type'],            name='ledger_ft_state_op_idx'),
            models.Index(fields=['state', 'updated_at'],         name='ledger_ft_state_updated_idx'),
            models.Index(fields=['context_type', 'context_id'],  name='ledger_ft_context_idx'),
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Shadow the loaded state so save() can detect direct assignments.
        self._committed_state: str = self.state
        # Flag set by transition_to() to allow the in-memory update after
        # the DB UPDATE WHERE succeeds.  Save() checks this flag.
        self._in_transition: bool = False

    def __str__(self):
        return f"FT-{self.id} [{self.op_type}/{self.state}] KES {self.amount}"

    def save(self, *args, **kwargs):
        """
        Block direct `.state = '...'` assignments on existing records.
        All state changes must go through transition_to() which holds the
        optimistic-lock UPDATE WHERE state = <expected>.
        """
        if (
            self.pk
            and self.state != self._committed_state
            and not self._in_transition
        ):
            raise TransitionError(
                f"FinancialTransaction {self.pk}: direct state assignment is not "
                f"allowed ({self._committed_state!r} → {self.state!r}). "
                "Use transition_to() instead."
            )
        super().save(*args, **kwargs)
        self._committed_state = self.state

    def transition_to(self, new_state: str, *,
                      failure_reason: str = '',
                      mpesa_receipt: str = '') -> None:
        """
        Atomically advance the state machine.

        Uses UPDATE WHERE state = <current> so two concurrent workers
        cannot both successfully transition the same record.
        Raises TransitionError on invalid graph edge or concurrent conflict.
        """
        if new_state not in self.VALID_TRANSITIONS.get(self.state, frozenset()):
            raise TransitionError(
                f"FinancialTransaction {self.id}: "
                f"invalid transition {self.state!r} → {new_state!r}. "
                f"Allowed from {self.state!r}: "
                f"{sorted(self.VALID_TRANSITIONS.get(self.state, set()))}"
            )

        update_kwargs: dict = {'state': new_state, 'updated_at': timezone.now()}
        if failure_reason:
            update_kwargs['failure_reason'] = failure_reason
        if mpesa_receipt:
            update_kwargs['mpesa_receipt'] = mpesa_receipt

        rows = FinancialTransaction.objects.filter(
            pk=self.pk, state=self.state,
        ).update(**update_kwargs)

        if rows == 0:
            raise TransitionError(
                f"FinancialTransaction {self.id}: "
                f"transition {self.state!r} → {new_state!r} lost concurrent race — "
                "another worker already advanced this record."
            )

        self._in_transition = True
        self.state = new_state
        self._committed_state = new_state
        self._in_transition = False
        if mpesa_receipt:
            self.mpesa_receipt = mpesa_receipt


class LedgerEntry(models.Model):
    """
    Immutable, append-only financial record.

    Every debit and credit is a separate row.
    NEVER update or delete rows — create a reversal entry instead.

    Balance = SUM(amount WHERE direction=CREDIT) - SUM(amount WHERE direction=DEBIT)
    """

    class Direction(models.TextChoices):
        CREDIT = 'CREDIT', 'Credit'   # money into the pool
        DEBIT  = 'DEBIT',  'Debit'    # money out of the pool

    class EntryType(models.TextChoices):
        MEMBER_CONTRIBUTION  = 'MEMBER_CONTRIBUTION',  'Member Contribution'
        ADVANCE_REPAYMENT    = 'ADVANCE_REPAYMENT',    'Advance Repayment'
        WELFARE_CONTRIBUTION = 'WELFARE_CONTRIBUTION', 'Welfare Contribution'
        SHARES_PURCHASE      = 'SHARES_PURCHASE',      'Shares Purchase'
        REVERSAL_CREDIT      = 'REVERSAL_CREDIT',      'Reversal Credit'
        DISBURSEMENT         = 'DISBURSEMENT',         'Disbursement'
        STANDING_ORDER       = 'STANDING_ORDER',       'Standing Order Payout'
        ROSCA_PAYOUT         = 'ROSCA_PAYOUT',         'ROSCA Payout'
        ADVANCE_DISBURSEMENT = 'ADVANCE_DISBURSEMENT', 'Emergency Advance Disbursement'
        WELFARE_CLAIM        = 'WELFARE_CLAIM',        'Welfare Claim Disbursement'
        REVERSAL_DEBIT       = 'REVERSAL_DEBIT',       'Reversal Debit'

    # ── Context — exactly one should be set ──────────────────────────────────
    contribution = models.ForeignKey(
        'contributions.Contribution', null=True, blank=True,
        on_delete=models.PROTECT, related_name='ledger_entries',
    )
    welfare_fund = models.ForeignKey(
        'contributions.WelfareFund', null=True, blank=True,
        on_delete=models.PROTECT, related_name='ledger_entries',
    )
    shares_fund = models.ForeignKey(
        'contributions.SharesFund', null=True, blank=True,
        on_delete=models.PROTECT, related_name='ledger_entries',
    )

    user       = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='ledger_entries',
    )
    amount     = models.DecimalField(max_digits=14, decimal_places=2)
    direction  = models.CharField(max_length=6,  choices=Direction.choices)
    entry_type = models.CharField(max_length=30, choices=EntryType.choices)

    idempotency_key = models.CharField(max_length=128, unique=True, db_index=True)
    mpesa_receipt   = models.CharField(max_length=50,  null=True, blank=True, db_index=True)

    financial_transaction = models.ForeignKey(
        FinancialTransaction, on_delete=models.PROTECT, related_name='ledger_entries',
    )
    note       = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['contribution', 'direction', 'created_at'], name='ledger_le_contrib_dir_idx'),
            models.Index(fields=['welfare_fund',  'direction', 'created_at'], name='ledger_le_welfare_dir_idx'),
            models.Index(fields=['shares_fund',   'direction', 'created_at'], name='ledger_le_shares_dir_idx'),
            models.Index(fields=['user',           'created_at'],             name='ledger_le_user_idx'),
        ]

    def __str__(self):
        return f"LE-{self.id} [{self.direction}/{self.entry_type}] KES {self.amount}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError(
                "LedgerEntry is immutable — "
                "create a REVERSAL_CREDIT / REVERSAL_DEBIT entry instead of updating."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError(
            "LedgerEntry cannot be deleted — "
            "create a REVERSAL_CREDIT / REVERSAL_DEBIT entry instead."
        )
