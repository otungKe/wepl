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

from django.db.models import BigIntegerField, Case, Exists, F, OuterRef, Q, Subquery, Sum, When

from apps.ledger.models import FinancialTransaction, JournalEntry, JournalLine

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


# A voted payout is the group's spend (ADR-0027 §0.1): its journal draws every
# funded member's share, so which sub-ledgers moved no longer says who it was
# for. The requester — the FT's initiator — is the party it was paid to.
_GROUP_PAYOUT = Q(context_type='disbursement_request')
# Journals whose member-sub-ledger debits are each member's part of a group
# spend, not money paid out to that member.
_GROUP_SPEND_LINE = (Q(journal__financial_transaction__context_type='disbursement_request')
                     | Q(journal__op_type='POOL_EXPENSE'))


def member_history_qs(user, *, contribution=None):
    """FinancialTransactions whose posted journal touches an account owned by
    ``user`` — the member's contribution-fund money movements, newest first.

    A journal only has lines once money has actually posted, so this inherently
    excludes pending/failed transactions (the legacy log only held settled rows).
    """
    owned_line = JournalLine.objects.filter(
        journal__financial_transaction=OuterRef('pk'), account__owner=user)
    posted = JournalLine.objects.filter(journal__financial_transaction=OuterRef('pk'))
    qs = (FinancialTransaction.objects
          .filter(Exists(owned_line) | (_GROUP_PAYOUT & Q(initiated_by=user) & Exists(posted)),
                  contribution__isnull=False)
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
            .annotate(party_id=Case(
                When(_GROUP_PAYOUT, then=F('initiated_by_id')),
                default=Subquery(owned.values('account__owner_id')[:1]),
                output_field=BigIntegerField()))
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
    aggregates; ``tx_count`` counts distinct settled movements.

    A member's part of a group spend is not money they received: those debits
    are left out, and a voted payout counts once, in full, for its requester —
    unless its payout failed and the journal was reversed (ADR-0027 §0.1)."""
    agg = (JournalLine.objects
           .filter(account__owner=user, account__fund_type='contribution')
           .aggregate(contributed=Sum('amount', filter=Q(direction=CREDIT)),
                      received=Sum('amount', filter=Q(direction=DEBIT) & ~_GROUP_SPEND_LINE)))
    group_payouts = (FinancialTransaction.objects
                     .filter(_GROUP_PAYOUT, initiated_by=user, contribution__isnull=False)
                     .filter(Exists(JournalEntry.objects.filter(
                         financial_transaction=OuterRef('pk'), reverses__isnull=True)))
                     .exclude(Exists(JournalEntry.objects.filter(
                         financial_transaction=OuterRef('pk'), reverses__isnull=False)))
                     .aggregate(total=Sum('amount')))['total'] or Decimal('0')
    return {
        'total_contributed': agg['contributed'] or Decimal('0'),
        'total_received':    (agg['received'] or Decimal('0')) + group_payouts,
        'tx_count':          member_history_qs(user).count(),
    }
