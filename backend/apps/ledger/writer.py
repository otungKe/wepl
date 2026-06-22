"""
FinancialTransaction helper.

`FinancialTransaction` is the orchestration / state-machine layer. Money movement
itself lives in the double-entry ledger (`post_journal`); a JournalEntry links
back to its FinancialTransaction via `JournalEntry.financial_transaction`.

This module used to also write the legacy single-entry shadow ledger; that was
removed in P0-07 (ADR-0002) now that journals are the single book of record.
"""
import logging
from decimal import Decimal

from .models import FinancialTransaction

logger = logging.getLogger(__name__)


def create_fin_transaction(
    *,
    idempotency_key: str,
    op_type: str,
    amount: Decimal,
    initiated_by,
    recipient_phone: str = '',
    contribution=None,
    welfare_fund=None,
    shares_fund=None,
    context_type: str = '',
    context_id: int | None = None,
    note: str = '',
    initial_state: str = FinancialTransaction.State.PENDING,
) -> tuple['FinancialTransaction', bool]:
    """
    Get-or-create a FinancialTransaction by idempotency_key.
    Returns (ft, created).  Safe to call on retry.
    """
    # Stamp the tenant from the owning fund's community (Phase 6, P6-03). Null
    # when not resolvable — safe under RLS (shared) and replaced once threaded.
    tenant = None
    for fund in (contribution, welfare_fund, shares_fund):
        if fund is not None:
            tenant = getattr(getattr(fund, 'community', None), 'tenant', None)
            if tenant is not None:
                break

    ft, created = FinancialTransaction.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults=dict(
            op_type=op_type,
            state=initial_state,
            amount=amount,
            initiated_by=initiated_by,
            recipient_phone=recipient_phone,
            contribution=contribution,
            welfare_fund=welfare_fund,
            shares_fund=shares_fund,
            context_type=context_type,
            context_id=context_id,
            note=note,
            tenant=tenant,
        ),
    )
    return ft, created
