"""
Double-entry posting writer.

`post_journal()` is the ONLY sanctioned way to create JournalEntry / JournalLine
rows. It guarantees, atomically:

  • the double-entry invariant  Σdebit == Σcredit  (≥ 2 lines),
  • idempotency on idempotency_key (safe under Celery retry / concurrency),
  • a transactionally-consistent update of the AccountBalance projection.

The database independently re-checks the balance invariant at COMMIT via a
deferred constraint trigger (migration 0003), so this writer is the convenient
guard, not the only one.
"""
import logging
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.db.models import F

from .exceptions import UnbalancedJournalError
from .models import Account, AccountBalance, JournalEntry, JournalLine

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Line:
    """One leg of a journal. amount must be > 0; direction carries the sign."""
    account: Account
    direction: str            # JournalLine.Direction.DEBIT / .CREDIT
    amount: Decimal
    note: str = ''


def _q(amount) -> Decimal:
    """Coerce to Decimal without going through float."""
    return amount if isinstance(amount, Decimal) else Decimal(str(amount))


@transaction.atomic
def post_journal(
    *,
    idempotency_key: str,
    op_type: str,
    lines: list[Line],
    narration: str = '',
    financial_transaction=None,
    reverses: JournalEntry | None = None,
    created_by=None,
    posted_at=None,
) -> JournalEntry:
    """
    Post a balanced journal. Returns the JournalEntry (existing one on replay).

    Raises UnbalancedJournalError if the lines do not balance or there are < 2.
    """
    # ── Idempotency: if we've already posted this key, return it untouched ────
    existing = JournalEntry.objects.filter(idempotency_key=idempotency_key).first()
    if existing is not None:
        return existing

    # ── Validate the double-entry invariant in the app layer ─────────────────
    if len(lines) < 2:
        raise UnbalancedJournalError(
            f"Journal {idempotency_key!r} needs at least two lines, got {len(lines)}."
        )

    debit_total = Decimal('0')
    credit_total = Decimal('0')
    for ln in lines:
        amt = _q(ln.amount)
        if amt <= 0:
            raise UnbalancedJournalError(
                f"Journal {idempotency_key!r}: line amounts must be > 0, got {amt}."
            )
        if ln.direction == JournalLine.Direction.DEBIT:
            debit_total += amt
        elif ln.direction == JournalLine.Direction.CREDIT:
            credit_total += amt
        else:
            raise UnbalancedJournalError(
                f"Journal {idempotency_key!r}: invalid direction {ln.direction!r}."
            )

    if debit_total != credit_total:
        raise UnbalancedJournalError(
            f"Journal {idempotency_key!r} is unbalanced: "
            f"debit={debit_total} credit={credit_total}."
        )

    # ── Create the entry (idempotency_key unique → safe under races) ─────────
    defaults = dict(
        op_type=op_type,
        narration=narration,
        financial_transaction=financial_transaction,
        reverses=reverses,
        created_by=created_by,
    )
    # Only override the model's default=timezone.now when a value is supplied;
    # passing posted_at=None into defaults would write NULL into a NOT NULL
    # column rather than falling back to the field default.
    if posted_at is not None:
        defaults['posted_at'] = posted_at

    journal, created = JournalEntry.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults=defaults,
    )
    if not created:
        # A concurrent worker won the race between our SELECT and INSERT.
        return journal

    JournalLine.objects.bulk_create([
        JournalLine(
            journal=journal,
            account=ln.account,
            direction=ln.direction,
            amount=_q(ln.amount),
            note=ln.note,
        )
        for ln in lines
    ])

    _apply_to_projection(lines)

    logger.info(
        "Posted JE-%s [%s] key=%s lines=%d amount=%s",
        journal.id, op_type, idempotency_key, len(lines), debit_total,
    )
    return journal


def _apply_to_projection(lines: list[Line]) -> None:
    """
    Update AccountBalance for each affected account inside the current
    transaction. Aggregates multiple lines hitting the same account.
    """
    per_account: dict[int, list[Decimal]] = defaultdict(lambda: [Decimal('0'), Decimal('0')])
    accounts: dict[int, Account] = {}
    for ln in lines:
        amt = _q(ln.amount)
        accounts[ln.account.pk] = ln.account
        if ln.direction == JournalLine.Direction.DEBIT:
            per_account[ln.account.pk][0] += amt
        else:
            per_account[ln.account.pk][1] += amt

    for account_id, (d_total, c_total) in per_account.items():
        AccountBalance.objects.get_or_create(account=accounts[account_id])
        AccountBalance.objects.filter(account_id=account_id).update(
            debit_total=F('debit_total') + d_total,
            credit_total=F('credit_total') + c_total,
        )


def reverse_journal(
    original: JournalEntry,
    *,
    idempotency_key: str | None = None,
    op_type: str | None = None,
    narration: str = '',
    created_by=None,
    posted_at=None,
) -> JournalEntry:
    """
    Post the exact inverse of `original`, linked via `reverses`.

    Every DEBIT becomes a CREDIT and vice-versa, same amounts and accounts.
    Idempotent: defaults the key to "reversal-<original key>".
    """
    key = idempotency_key or f"reversal-{original.idempotency_key}"
    flip = {
        JournalLine.Direction.DEBIT:  JournalLine.Direction.CREDIT,
        JournalLine.Direction.CREDIT: JournalLine.Direction.DEBIT,
    }
    lines = [
        Line(
            account=jl.account,
            direction=flip[jl.direction],
            amount=jl.amount,
            note=f"Reversal of JL-{jl.id}",
        )
        for jl in original.lines.select_related('account').all()
    ]
    return post_journal(
        idempotency_key=key,
        op_type=op_type or f"REVERSAL_{original.op_type}",
        lines=lines,
        narration=narration or f"Reversal of JE-{original.id}",
        financial_transaction=original.financial_transaction,
        reverses=original,
        created_by=created_by,
        posted_at=posted_at,
    )
