"""
Balance reads and reconciliation for the double-entry core.

Two ways to obtain a balance:

  • account_balance(account)        — O(1) read from the AccountBalance cache.
  • replay_account_balance(account) — authoritative recompute from immutable
                                      JournalLines (source of truth).

reconcile_account() asserts the two agree; recompute_account_balance() rebuilds
the cache from the lines. Together these make the projection safe to trust and
trivial to repair.
"""
from decimal import Decimal

from django.db import transaction
from django.db.models import Case, DecimalField, F, Sum, When

from .models import Account, AccountBalance, JournalLine


def _replay_totals(account: Account) -> tuple[Decimal, Decimal]:
    """(debit_total, credit_total) summed from raw lines for one account."""
    agg = JournalLine.objects.filter(account=account).aggregate(
        debit=Sum(
            Case(
                When(direction=JournalLine.Direction.DEBIT, then=F('amount')),
                default=Decimal('0'),
                output_field=DecimalField(max_digits=20, decimal_places=4),
            )
        ),
        credit=Sum(
            Case(
                When(direction=JournalLine.Direction.CREDIT, then=F('amount')),
                default=Decimal('0'),
                output_field=DecimalField(max_digits=20, decimal_places=4),
            )
        ),
    )
    return agg['debit'] or Decimal('0'), agg['credit'] or Decimal('0')


def replay_account_balance(account: Account) -> Decimal:
    """Authoritative normal-balance figure recomputed from immutable lines."""
    debit, credit = _replay_totals(account)
    return account.signed(debit, credit)


def account_balance(account: Account) -> Decimal:
    """Fast normal-balance figure from the AccountBalance projection.

    Reads the projection row fresh rather than through ``account.balance`` (the
    reverse one-to-one accessor): the posting writer updates the row via a
    queryset ``F()`` UPDATE, which does not refresh any cached reverse relation
    already attached to the passed-in ``account`` instance.
    """
    ab = AccountBalance.objects.filter(account=account).first()
    if ab is None:
        return Decimal('0')
    return account.signed(ab.debit_total, ab.credit_total)


def fund_balance(fund_type: str, fund_id: int) -> Decimal:
    """Pool balance of a fund = signed sum over its member sub-ledger accounts.

    The member sub-ledgers for contribution / welfare / shares funds are all
    LIABILITY (credit-normal), so the pool we owe members is ``Σcredit − Σdebit``
    across those accounts. This is the ledger-derived replacement for the legacy
    mutable fields (`Contribution.current_amount`, `WelfareFund.balance`,
    `SharesFund.total_pool`).
    """
    agg = AccountBalance.objects.filter(
        account__fund_type=fund_type, account__fund_id=fund_id,
    ).aggregate(d=Sum('debit_total'), c=Sum('credit_total'))
    return (agg['c'] or Decimal('0')) - (agg['d'] or Decimal('0'))


def fund_balances(fund_type: str, fund_ids) -> dict:
    """{fund_id: pool balance} for many funds of one type, in one query."""
    out: dict = {}
    for row in (
        AccountBalance.objects
        .filter(account__fund_type=fund_type, account__fund_id__in=list(fund_ids))
        .values('account__fund_id')
        .annotate(d=Sum('debit_total'), c=Sum('credit_total'))
    ):
        out[row['account__fund_id']] = (row['c'] or Decimal('0')) - (row['d'] or Decimal('0'))
    return out


def member_fund_balance(user, fund_type: str, fund_id: int) -> Decimal:
    """A single member's signed sub-ledger balance in a fund (0 if none).

    Read-only: never creates an Account (unlike ``coa.member_fund_account``), so
    it is safe to call from serializers / GET paths. Member sub-ledgers for
    contribution / welfare / shares are LIABILITY (credit-normal).
    """
    agg = AccountBalance.objects.filter(
        account__owner=user, account__fund_type=fund_type, account__fund_id=fund_id,
    ).aggregate(d=Sum('debit_total'), c=Sum('credit_total'))
    return (agg['c'] or Decimal('0')) - (agg['d'] or Decimal('0'))


def org_fund_balance(org, fund_type: str, fund_id: int) -> Decimal:
    """An organization's signed sub-ledger balance in a fund (0 if none).

    The org-owned analogue of ``member_fund_balance`` (ADR-0027). Read-only —
    never creates an Account. Org sub-ledgers are LIABILITY (credit-normal).
    """
    agg = AccountBalance.objects.filter(
        account__owner_org=org, account__fund_type=fund_type, account__fund_id=fund_id,
    ).aggregate(d=Sum('debit_total'), c=Sum('credit_total'))
    return (agg['c'] or Decimal('0')) - (agg['d'] or Decimal('0'))


def economic_interest(party, fund_type: str, fund_id: int) -> Decimal:
    """A party's *derived* economic interest in a fund (ADR-0027).

    Economic interest is a view, never a stored value. Today every fund is a
    ``debt`` claim-type, so a party's interest equals their redeemable liability
    sub-ledger balance (``member_fund_balance``). This is the single seam where
    equity (units × NAV) derivation plugs in when a fund graduates to unit/NAV
    accounting — callers ask "what is X's economic interest here?" rather than
    reading a raw account balance, so the graduation is transparent to them.
    """
    return member_fund_balance(party, fund_type, fund_id)


def user_fund_balances(user, fund_type: str, fund_ids=None) -> dict:
    """{fund_id: signed balance} for one user across many funds, in one query.

    Used to avoid N+1 when serialising a list of contributions for a user.
    """
    qs = AccountBalance.objects.filter(account__owner=user, account__fund_type=fund_type)
    if fund_ids is not None:
        qs = qs.filter(account__fund_id__in=list(fund_ids))
    out: dict = {}
    for row in qs.values('account__fund_id').annotate(
        d=Sum('debit_total'), c=Sum('credit_total')
    ):
        out[row['account__fund_id']] = (row['c'] or Decimal('0')) - (row['d'] or Decimal('0'))
    return out


def fund_member_balances(fund_type: str, fund_id: int) -> dict:
    """{user_id: signed balance} for every member of one fund, in one query."""
    out: dict = {}
    for row in (
        AccountBalance.objects
        .filter(account__fund_type=fund_type, account__fund_id=fund_id)
        .values('account__owner_id')
        .annotate(d=Sum('debit_total'), c=Sum('credit_total'))
    ):
        out[row['account__owner_id']] = (row['c'] or Decimal('0')) - (row['d'] or Decimal('0'))
    return out


@transaction.atomic
def recompute_account_balance(account: Account) -> AccountBalance:
    """Rebuild the projection for one account from its lines. Repair primitive."""
    debit, credit = _replay_totals(account)
    ab, _ = AccountBalance.objects.get_or_create(account=account)
    AccountBalance.objects.filter(account=account).update(
        debit_total=debit, credit_total=credit,
    )
    ab.refresh_from_db()
    return ab


def reconcile_account(account: Account) -> dict:
    """
    Compare projection against replay for one account.

    Returns a dict describing the result; `ok` is True when they agree.
    Used by a scheduled reconciliation job and by tests.
    """
    replay_debit, replay_credit = _replay_totals(account)
    # Read the projection fresh (not via the cached reverse accessor) so a row
    # mutated by the posting writer's F() UPDATE is reflected here.
    ab = AccountBalance.objects.filter(account=account).first()
    cached = (ab.debit_total, ab.credit_total) if ab else (Decimal('0'), Decimal('0'))

    ok = cached == (replay_debit, replay_credit)
    return {
        'account': account.code,
        'ok': ok,
        'cached_debit': cached[0],
        'cached_credit': cached[1],
        'replay_debit': replay_debit,
        'replay_credit': replay_credit,
    }


def trial_balance() -> dict:
    """
    Global trial balance from the source-of-truth lines.

    Returns total debits, total credits, and whether the books balance.
    In a correct double-entry system total_debit == total_credit always.
    """
    agg = JournalLine.objects.aggregate(
        total_debit=Sum(
            Case(
                When(direction=JournalLine.Direction.DEBIT, then=F('amount')),
                default=Decimal('0'),
                output_field=DecimalField(max_digits=20, decimal_places=4),
            )
        ),
        total_credit=Sum(
            Case(
                When(direction=JournalLine.Direction.CREDIT, then=F('amount')),
                default=Decimal('0'),
                output_field=DecimalField(max_digits=20, decimal_places=4),
            )
        ),
    )
    td = agg['total_debit'] or Decimal('0')
    tc = agg['total_credit'] or Decimal('0')
    return {'total_debit': td, 'total_credit': tc, 'balanced': td == tc}
