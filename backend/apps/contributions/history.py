"""Ledger-derived member money history (retires ContributionTransaction).

A member's transaction history is derived from the immutable ledger — the
``FinancialTransaction``s whose posted journal touches an account the member
*owns* — never from a per-member shadow log. This is attribution-safe: a
contribution gifted to a member surfaces on the *beneficiary's* history because
their sub-ledger is the account that actually moved (ADR-0027).

Scope matches what the legacy log covered: contribution-fund movements
(contributions, withdrawals/payouts) and the advances tied to a contribution.
"""
from __future__ import annotations

from decimal import Decimal

from django.db.models import Exists, OuterRef, Q, Subquery, Sum

from apps.ledger.models import FinancialTransaction, JournalLine

CREDIT = JournalLine.Direction.CREDIT
DEBIT = JournalLine.Direction.DEBIT

# FinancialTransaction.op_type → the member-facing transaction_type the legacy
# ContributionTransaction exposed. Money direction on the member's sub-ledger is
# the source of truth; this is only the display label.
_OP_TO_TYPE = {
    'CONTRIBUTION':         'CONTRIBUTION',
    'SHARES_PURCHASE':      'CONTRIBUTION',
    'WELFARE_CONTRIBUTION': 'CONTRIBUTION',
    'STANDING_ORDER':       'WITHDRAWAL',
    'DISBURSEMENT':         'WITHDRAWAL',
    'ROSCA_PAYOUT':         'WITHDRAWAL',
    'WELFARE_CLAIM':        'WITHDRAWAL',
    'ADVANCE_DISBURSEMENT': 'ADVANCE',
    'ADVANCE_REPAYMENT':    'REPAYMENT',
}


def transaction_type_for(op_type: str) -> str:
    return _OP_TO_TYPE.get(op_type, 'CONTRIBUTION')


def member_history_qs(user, *, contribution=None):
    """FinancialTransactions whose posted journal touches an account owned by
    ``user`` — the member's contribution-fund money movements, newest first.

    A journal only has lines once money has actually posted, so this inherently
    excludes pending/failed transactions (the legacy log only held settled rows).
    """
    owned_line = JournalLine.objects.filter(
        journal__financial_transaction=OuterRef('pk'), account__owner=user)
    qs = (FinancialTransaction.objects
          .filter(Exists(owned_line), contribution__isnull=False)
          .select_related('contribution')
          .order_by('-created_at', '-id'))
    if contribution is not None:
        qs = qs.filter(contribution=contribution)
    return qs


def contribution_history_qs(contribution):
    """Every settled money movement on one contribution, newest first, annotated
    with ``party_id`` — the member whose sub-ledger moved (the economic party of
    that transaction). Used by the shared-visibility list, where each row can
    belong to a different member.
    """
    owned = JournalLine.objects.filter(
        journal__financial_transaction=OuterRef('pk'), account__owner__isnull=False)
    return (FinancialTransaction.objects
            .filter(Exists(owned), contribution=contribution)
            .annotate(party_id=Subquery(owned.values('account__owner_id')[:1]))
            .select_related('contribution')
            .order_by('-created_at', '-id'))


def member_contribution_credits(user):
    """JournalLine CREDITs to the member's contribution sub-ledgers — i.e. money
    the member contributed in (the ledger-true basis for contribution totals and
    trends). Debits are payouts back to them."""
    return JournalLine.objects.filter(
        account__owner=user, account__fund_type='contribution', direction=CREDIT)


def member_summary(user) -> dict:
    """Contribution-fund totals for a member, derived from their sub-ledger lines
    (credits = contributed in, debits = received out). Replaces the legacy CT
    aggregates; ``tx_count`` counts distinct settled movements."""
    agg = (JournalLine.objects
           .filter(account__owner=user, account__fund_type='contribution')
           .aggregate(contributed=Sum('amount', filter=Q(direction=CREDIT)),
                      received=Sum('amount', filter=Q(direction=DEBIT))))
    return {
        'total_contributed': agg['contributed'] or Decimal('0'),
        'total_received':    agg['received'] or Decimal('0'),
        'tx_count':          member_history_qs(user).count(),
    }
