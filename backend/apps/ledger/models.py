"""
Financial ledger — the single source of truth for all money movements.

FinancialTransaction  — one complete financial event with a strict state machine
                        (orchestration layer; links to the journal that moved the
                        money). The legacy single-entry shadow ledger was removed
                        in P0-07 (ADR-0002).

Double-entry core (the accounting source of truth):
    Account       — every place money can rest (GL classification + member
                    sub-ledgers that roll up to a GL parent).
    JournalEntry  — one balanced financial event.
    JournalLine   — an immutable debit/credit against a single Account.
    AccountBalance— a rebuildable projection (cache) of an account's totals.

Balances are ALWAYS derived from immutable lines. Mutable balance fields and
the AccountBalance projection exist only as a performance cache and can be
reconstructed at any time by replaying JournalLines.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.exceptions import TransitionError
from apps.ledger.exceptions import JournalImmutableError


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



# ═══════════════════════════════════════════════════════════════════════════
# DOUBLE-ENTRY CORE
# ═══════════════════════════════════════════════════════════════════════════
#
# The classical accounting equation, enforced structurally:
#
#       ASSETS = LIABILITIES + EQUITY + (INCOME − EXPENSE)
#
# Every financial event is a JournalEntry whose JournalLines satisfy
#       Σ(debit amounts) = Σ(credit amounts).
#
# Account balance, by normal balance side:
#       debit-normal  (ASSET, EXPENSE):  balance = Σdebit − Σcredit
#       credit-normal (LIABILITY,        balance = Σcredit − Σdebit
#                      EQUITY, INCOME)
# ═══════════════════════════════════════════════════════════════════════════


class Account(models.Model):
    """
    A node in the Chart of Accounts.

    One table serves two roles, distinguished by whether `owner`/`fund_*` are set:

      • GL accounts        — the canonical classification accounts
                             (M-Pesa Float, Member Contributions Payable,
                              Fee Revenue, Suspense, …). `parent` is null.
      • Sub-ledger accounts— one per member-per-fund. `parent` points at the
                             GL account they roll up into, so a pool balance is
                             simply the parent's balance and a member balance is
                             the child's.

    Identity lives in `code` (unique), which makes account resolution idempotent:
    the same logical account always resolves to the same row.
    """

    class Type(models.TextChoices):
        ASSET     = 'ASSET',     'Asset'
        LIABILITY = 'LIABILITY', 'Liability'
        EQUITY    = 'EQUITY',    'Equity'
        INCOME    = 'INCOME',    'Income'
        EXPENSE   = 'EXPENSE',   'Expense'

    # Types whose balance increases on the DEBIT side.
    DEBIT_NORMAL_TYPES = frozenset({Type.ASSET, Type.EXPENSE})

    code = models.CharField(
        max_length=64, unique=True,
        help_text="Stable Chart-of-Accounts code; account resolution keys on this.",
    )
    name   = models.CharField(max_length=255)
    type   = models.CharField(max_length=10, choices=Type.choices)
    parent = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.PROTECT, related_name='children',
    )

    # ── Sub-ledger ownership (null for pure GL accounts) ──────────────────────
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.PROTECT, related_name='ledger_accounts',
    )
    # Generic link to the owning fund, stored as primitives to avoid circular
    # FK imports and to keep the ledger independent of fund-type schemas.
    # fund_type ∈ {'', 'contribution', 'welfare', 'shares', ...}
    fund_type = models.CharField(max_length=30, blank=True)
    fund_id   = models.PositiveIntegerField(null=True, blank=True)

    currency  = models.CharField(max_length=3, default='KES')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['type'],                        name='ledger_acct_type_idx'),
            models.Index(fields=['fund_type', 'fund_id'],        name='ledger_acct_fund_idx'),
            models.Index(fields=['owner', 'fund_type', 'fund_id'], name='ledger_acct_owner_fund_idx'),
        ]

    @property
    def is_debit_normal(self) -> bool:
        return self.type in self.DEBIT_NORMAL_TYPES

    def signed(self, debit_total: Decimal, credit_total: Decimal) -> Decimal:
        """Convert raw debit/credit totals into a normal-balance-aware figure."""
        if self.is_debit_normal:
            return debit_total - credit_total
        return credit_total - debit_total

    def __str__(self):
        return f"{self.code} · {self.name} [{self.type}]"


class JournalEntry(models.Model):
    """
    One balanced financial event. Immutable once posted.

    A journal groups ≥2 JournalLines that net to zero. It optionally links to a
    FinancialTransaction (the orchestration/state-machine layer) and, for
    corrections, to the JournalEntry it reverses — corrections are always new
    entries, never mutations.
    """

    idempotency_key = models.CharField(max_length=128, unique=True, db_index=True)
    op_type   = models.CharField(
        max_length=40,
        help_text="Business operation, e.g. CONTRIBUTION, DISBURSEMENT, FEE, ADJUSTMENT.",
    )
    narration = models.TextField(blank=True)

    # Orchestration linkage (nullable: manual adjustments / opening balances
    # have no FinancialTransaction).
    financial_transaction = models.ForeignKey(
        'ledger.FinancialTransaction', null=True, blank=True,
        on_delete=models.PROTECT, related_name='journals',
    )
    # Reversal linkage — never mutate, only reverse.
    reverses = models.ForeignKey(
        'self', null=True, blank=True,
        on_delete=models.PROTECT, related_name='reversed_by',
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.PROTECT, related_name='posted_journals',
    )
    posted_at  = models.DateTimeField(
        default=timezone.now,
        help_text="Accounting/value date — may differ from created_at.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['op_type', 'posted_at'], name='ledger_je_optype_posted_idx'),
        ]
        verbose_name_plural = 'Journal entries'

    def __str__(self):
        return f"JE-{self.id} [{self.op_type}]"

    def save(self, *args, **kwargs):
        if self.pk:
            raise JournalImmutableError(
                f"JournalEntry {self.pk} is immutable — post a reversing entry "
                "(reverses=<original>) instead of editing it."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise JournalImmutableError(
            "JournalEntry cannot be deleted — post a reversing entry instead."
        )


class JournalLine(models.Model):
    """
    A single immutable debit or credit against one Account.

    Amounts are ALWAYS positive; the `direction` carries the sign. This removes
    a whole class of sign-handling bugs and makes the balance trigger trivial.
    """

    class Direction(models.TextChoices):
        DEBIT  = 'DEBIT',  'Debit'
        CREDIT = 'CREDIT', 'Credit'

    journal   = models.ForeignKey(
        JournalEntry, on_delete=models.PROTECT, related_name='lines',
    )
    account   = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name='lines',
    )
    direction = models.CharField(max_length=6, choices=Direction.choices)
    amount    = models.DecimalField(max_digits=20, decimal_places=4)
    note      = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0), name='ledger_jl_amount_positive',
            ),
        ]
        indexes = [
            models.Index(fields=['account', 'created_at'], name='ledger_jl_account_created_idx'),
            models.Index(fields=['journal'],               name='ledger_jl_journal_idx'),
        ]

    def __str__(self):
        return f"JL-{self.id} {self.direction} {self.amount} → {self.account_id}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise JournalImmutableError(
                "JournalLine is immutable — post a reversing JournalEntry instead."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise JournalImmutableError(
            "JournalLine cannot be deleted — post a reversing JournalEntry instead."
        )


class AccountBalance(models.Model):
    """
    A rebuildable projection of an Account's running totals.

    This is a CACHE, not a source of truth: it is updated transactionally by the
    posting writer and can be fully reconstructed at any time by replaying
    JournalLines (see balances.recompute_account_balance). A nightly job that
    asserts projection == replay is both the performance strategy and a
    continuous reconciliation control.
    """

    account      = models.OneToOneField(
        Account, on_delete=models.PROTECT, related_name='balance',
    )
    debit_total  = models.DecimalField(max_digits=20, decimal_places=4, default=Decimal('0'))
    credit_total = models.DecimalField(max_digits=20, decimal_places=4, default=Decimal('0'))
    updated_at   = models.DateTimeField(auto_now=True)

    @property
    def balance(self) -> Decimal:
        """Normal-balance-aware signed balance."""
        return self.account.signed(self.debit_total, self.credit_total)

    def __str__(self):
        return f"Bal({self.account.code}) = {self.balance}"
