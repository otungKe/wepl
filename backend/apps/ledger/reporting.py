"""
Financial reporting from the double-entry general ledger (Phase 4).

Every figure here is computed from immutable ``JournalLine`` rows — the source of
truth — never from the ``AccountBalance`` cache, so reports are reproducible from
the lines at any past point in time (pass ``as_of``). All reports reconcile to the
ledger to the cent; a correct ledger always has a zero global trial balance.

Dimensions: every report accepts optional ``fund_type`` / ``fund_id`` / ``op_type``
filters so statements can be produced per community/fund.
"""
from decimal import Decimal

from django.db.models import Case, DecimalField, F, Sum, When

from .models import Account, JournalEntry, JournalLine

_DEC = DecimalField(max_digits=20, decimal_places=4)
_ZERO = Decimal('0')


def _debit_expr():
    return Sum(Case(When(direction=JournalLine.Direction.DEBIT, then=F('amount')),
                    default=_ZERO, output_field=_DEC))


def _credit_expr():
    return Sum(Case(When(direction=JournalLine.Direction.CREDIT, then=F('amount')),
                    default=_ZERO, output_field=_DEC))


def _signed(acct_type: str, debit: Decimal, credit: Decimal) -> Decimal:
    """Normal-balance figure for an account type."""
    if acct_type in Account.DEBIT_NORMAL_TYPES:
        return (debit or _ZERO) - (credit or _ZERO)
    return (credit or _ZERO) - (debit or _ZERO)


def _lines(*, as_of=None, start=None, end=None, fund_type=None, fund_id=None, op_type=None):
    qs = JournalLine.objects.all()
    if as_of is not None:
        qs = qs.filter(journal__posted_at__lte=as_of)
    if start is not None:
        qs = qs.filter(journal__posted_at__gte=start)
    if end is not None:
        qs = qs.filter(journal__posted_at__lte=end)
    if op_type:
        qs = qs.filter(journal__op_type=op_type)
    if fund_type is not None:
        qs = qs.filter(account__fund_type=fund_type)
    if fund_id is not None:
        qs = qs.filter(account__fund_id=fund_id)
    return qs


# ── P4-01 Trial balance ──────────────────────────────────────────────────────
def trial_balance(*, as_of=None, fund_type=None, fund_id=None, op_type=None) -> dict:
    """Per-account debit/credit/normal-balance plus totals and balanced flag."""
    rows = []
    total_debit = total_credit = _ZERO
    per = (
        _lines(as_of=as_of, fund_type=fund_type, fund_id=fund_id, op_type=op_type)
        .values('account__code', 'account__name', 'account__type')
        .annotate(debit=_debit_expr(), credit=_credit_expr())
        .order_by('account__code')
    )
    for r in per:
        d, c = r['debit'] or _ZERO, r['credit'] or _ZERO
        total_debit += d
        total_credit += c
        rows.append({
            'code': r['account__code'], 'name': r['account__name'], 'type': r['account__type'],
            'debit': d, 'credit': c, 'balance': _signed(r['account__type'], d, c),
        })
    return {
        'as_of': as_of, 'rows': rows,
        'total_debit': total_debit, 'total_credit': total_credit,
        'balanced': total_debit == total_credit,
    }


# ── P4-02 Balance sheet & income statement ───────────────────────────────────
def _totals_by_type(qs) -> dict:
    out = {}
    for r in qs.values('account__type').annotate(debit=_debit_expr(), credit=_credit_expr()):
        out[r['account__type']] = _signed(r['account__type'], r['debit'] or _ZERO, r['credit'] or _ZERO)
    return out


def balance_sheet(*, as_of=None, fund_type=None, fund_id=None) -> dict:
    """Assets = Liabilities + Equity + retained earnings (cumulative net income)."""
    t = _totals_by_type(_lines(as_of=as_of, fund_type=fund_type, fund_id=fund_id))
    assets = t.get(Account.Type.ASSET, _ZERO)
    liabilities = t.get(Account.Type.LIABILITY, _ZERO)
    equity = t.get(Account.Type.EQUITY, _ZERO)
    income = t.get(Account.Type.INCOME, _ZERO)
    expense = t.get(Account.Type.EXPENSE, _ZERO)
    retained = income - expense  # net income folds into equity
    return {
        'as_of': as_of,
        'assets': assets,
        'liabilities': liabilities,
        'equity': equity,
        'retained_earnings': retained,
        'total_equity': equity + retained,
        'balanced': assets == liabilities + equity + retained,
    }


def income_statement(*, start=None, end=None, fund_type=None, fund_id=None) -> dict:
    """Income, expense and net for a period (per account + totals)."""
    qs = _lines(start=start, end=end, fund_type=fund_type, fund_id=fund_id).filter(
        account__type__in=[Account.Type.INCOME, Account.Type.EXPENSE]
    )
    income_rows, expense_rows = [], []
    income_total = expense_total = _ZERO
    for r in (qs.values('account__code', 'account__name', 'account__type')
              .annotate(debit=_debit_expr(), credit=_credit_expr()).order_by('account__code')):
        bal = _signed(r['account__type'], r['debit'] or _ZERO, r['credit'] or _ZERO)
        row = {'code': r['account__code'], 'name': r['account__name'], 'amount': bal}
        if r['account__type'] == Account.Type.INCOME:
            income_rows.append(row); income_total += bal
        else:
            expense_rows.append(row); expense_total += bal
    return {
        'start': start, 'end': end,
        'income': income_rows, 'expense': expense_rows,
        'income_total': income_total, 'expense_total': expense_total,
        'net_income': income_total - expense_total,
    }


# ── P4-03 Statement of account ───────────────────────────────────────────────
def statement_of_account(account: Account, *, start=None, end=None) -> dict:
    """Opening balance, period lines with a running balance, and closing balance."""
    debit_normal = account.type in Account.DEBIT_NORMAL_TYPES

    def _delta(direction, amount):
        inc = (direction == JournalLine.Direction.DEBIT) if debit_normal else (direction == JournalLine.Direction.CREDIT)
        return amount if inc else -amount

    # Opening balance = signed balance strictly before `start`.
    opening = _ZERO
    if start is not None:
        agg = (JournalLine.objects.filter(account=account, journal__posted_at__lt=start)
               .aggregate(debit=_debit_expr(), credit=_credit_expr()))
        opening = _signed(account.type, agg['debit'] or _ZERO, agg['credit'] or _ZERO)

    qs = JournalLine.objects.filter(account=account).select_related('journal')
    if start is not None:
        qs = qs.filter(journal__posted_at__gte=start)
    if end is not None:
        qs = qs.filter(journal__posted_at__lte=end)
    qs = qs.order_by('journal__posted_at', 'id')

    running = opening
    entries = []
    for ln in qs:
        running += _delta(ln.direction, ln.amount)
        entries.append({
            'date': ln.journal.posted_at, 'op_type': ln.journal.op_type,
            'narration': ln.journal.narration, 'direction': ln.direction,
            'amount': ln.amount, 'balance': running,
        })
    return {
        'account': account.code, 'account_name': account.name,
        'start': start, 'end': end,
        'opening_balance': opening, 'entries': entries, 'closing_balance': running,
    }


def member_account(user, fund_type: str, fund_id: int) -> Account | None:
    """Resolve a member's sub-ledger account read-only (None if none yet)."""
    return Account.objects.filter(owner=user, fund_type=fund_type, fund_id=fund_id).first()


# ── P5-04 Per-currency trial balance + presentation consolidation ────────────
def trial_balance_by_currency(*, as_of=None, fund_type=None, fund_id=None, op_type=None) -> dict:
    """Trial balance split by account currency; each currency must self-balance."""
    out: dict[str, dict] = {}
    per = (
        _lines(as_of=as_of, fund_type=fund_type, fund_id=fund_id, op_type=op_type)
        .values('account__currency')
        .annotate(debit=_debit_expr(), credit=_credit_expr())
    )
    for r in per:
        d, c = r['debit'] or _ZERO, r['credit'] or _ZERO
        out[r['account__currency']] = {
            'total_debit': d, 'total_credit': c, 'balanced': d == c,
        }
    return {
        'as_of': as_of,
        'currencies': out,
        'balanced': all(v['balanced'] for v in out.values()),
    }


def present_value(amount: Decimal, currency: str, presentation: str, *, at=None) -> Decimal:
    """Convert a single-currency figure into a presentation currency for
    consolidated reporting (uses the effective-dated FX table)."""
    from .fx import get_rate
    if currency == presentation:
        return amount
    return amount * get_rate(currency, presentation, at=at)


# ── P4-04 Audit export ───────────────────────────────────────────────────────
EXPORT_COLUMNS = (
    'journal_id', 'posted_at', 'op_type', 'idempotency_key', 'narration',
    'reverses_id', 'line_id', 'account_code', 'account_name', 'direction', 'amount',
)


def export_journal_rows(*, start=None, end=None):
    """Yield one flat dict per journal line — the immutable audit trail.

    Joined journal+line view suitable for CSV/JSON export to an auditor.
    """
    qs = JournalLine.objects.select_related('journal', 'account').order_by('journal__posted_at', 'journal_id', 'id')
    if start is not None:
        qs = qs.filter(journal__posted_at__gte=start)
    if end is not None:
        qs = qs.filter(journal__posted_at__lte=end)
    for ln in qs.iterator():
        je: JournalEntry = ln.journal
        yield {
            'journal_id': je.id,
            'posted_at': je.posted_at.isoformat(),
            'op_type': je.op_type,
            'idempotency_key': je.idempotency_key,
            'narration': je.narration,
            'reverses_id': je.reverses_id,
            'line_id': ln.id,
            'account_code': ln.account.code,
            'account_name': ln.account.name,
            'direction': ln.direction,
            'amount': str(ln.amount),
        }
