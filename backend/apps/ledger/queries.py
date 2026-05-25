"""
Balance derivation — always computed from ledger entries, never from mutable fields.

Import and call these functions wherever you need a balance.
Never read Contribution.current_amount / WelfareFund.balance directly in new code.
"""
from decimal import Decimal

from django.db.models import Case, DecimalField, F, Sum, When

from .models import LedgerEntry


def _signed_sum(qs) -> Decimal:
    """Sum ledger entries treating CREDIT as +, DEBIT as -."""
    result = qs.aggregate(
        balance=Sum(
            Case(
                When(direction=LedgerEntry.Direction.CREDIT, then=F('amount')),
                When(direction=LedgerEntry.Direction.DEBIT,  then=-F('amount')),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            )
        )
    )
    return result['balance'] or Decimal('0')


def contribution_balance(contribution_id: int) -> Decimal:
    """Current pool balance for a contribution group."""
    return _signed_sum(
        LedgerEntry.objects.filter(contribution_id=contribution_id)
    )


def welfare_fund_balance(welfare_fund_id: int) -> Decimal:
    """Current balance of a welfare fund."""
    return _signed_sum(
        LedgerEntry.objects.filter(welfare_fund_id=welfare_fund_id)
    )


def shares_fund_balance(shares_fund_id: int) -> Decimal:
    """Current total pool of a shares fund."""
    return _signed_sum(
        LedgerEntry.objects.filter(shares_fund_id=shares_fund_id)
    )


def member_contribution_total(contribution_id: int, user_id: int) -> Decimal:
    """
    Total net credits for a specific member in a contribution group.
    Used for advance eligibility (max 80% of own contributions).
    Counts MEMBER_CONTRIBUTION + ADVANCE_REPAYMENT credits only —
    not reversal credits or other one-off entries.
    """
    result = LedgerEntry.objects.filter(
        contribution_id=contribution_id,
        user_id=user_id,
        direction=LedgerEntry.Direction.CREDIT,
        entry_type__in=[
            LedgerEntry.EntryType.MEMBER_CONTRIBUTION,
            LedgerEntry.EntryType.ADVANCE_REPAYMENT,
        ],
    ).aggregate(total=Sum('amount'))
    return result['total'] or Decimal('0')
