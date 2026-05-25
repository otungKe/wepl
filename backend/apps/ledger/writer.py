"""
Idempotent ledger writer.

All code that creates LedgerEntry or FinancialTransaction rows must go
through these helpers — never construct those models directly.

Both functions are safe to call multiple times with the same idempotency_key
(e.g. on Celery task retry). If the key already exists the existing record is
returned and a collision-safety check is performed.
"""
import logging
from decimal import Decimal

from .models import FinancialTransaction, LedgerEntry

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
        ),
    )
    return ft, created


def write_ledger_entry(
    *,
    idempotency_key: str,
    financial_transaction: 'FinancialTransaction',
    user,
    amount: Decimal,
    direction: str,
    entry_type: str,
    contribution=None,
    welfare_fund=None,
    shares_fund=None,
    mpesa_receipt: str | None = None,
    note: str = '',
) -> tuple['LedgerEntry', bool]:
    """
    Get-or-create a LedgerEntry by idempotency_key.
    Returns (entry, created).  Safe to call on retry.

    Raises ValueError if the key exists but with different amount/direction —
    that indicates a programming error or a collision requiring manual review.
    """
    entry, created = LedgerEntry.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults=dict(
            financial_transaction=financial_transaction,
            user=user,
            amount=amount,
            direction=direction,
            entry_type=entry_type,
            contribution=contribution,
            welfare_fund=welfare_fund,
            shares_fund=shares_fund,
            mpesa_receipt=mpesa_receipt,
            note=note,
        ),
    )

    if not created:
        if entry.amount != amount or entry.direction != direction:
            logger.critical(
                "LedgerEntry idempotency collision on key %r: "
                "existing=(amount=%s dir=%s) vs new=(amount=%s dir=%s). "
                "Manual review required.",
                idempotency_key, entry.amount, entry.direction, amount, direction,
            )
            raise ValueError(
                f"Idempotency key {idempotency_key!r} already exists with different "
                "financial parameters — this is a critical data inconsistency."
            )

    return entry, created


def write_reversal_credit(ft: 'FinancialTransaction', *, note: str = '') -> 'LedgerEntry':
    """
    Write a REVERSAL_CREDIT to restore funds when a payout fails.
    Idempotent — safe to call multiple times for the same FT.
    """
    key = f"reversal-credit-{ft.idempotency_key}"
    kwargs: dict = dict(
        idempotency_key=key,
        financial_transaction=ft,
        user=ft.initiated_by,
        amount=ft.amount,
        direction=LedgerEntry.Direction.CREDIT,
        entry_type=LedgerEntry.EntryType.REVERSAL_CREDIT,
        note=note or f"Reversal of failed {ft.op_type} (FT-{ft.id})",
    )
    if ft.contribution_id:
        kwargs['contribution_id'] = ft.contribution_id
    elif ft.welfare_fund_id:
        kwargs['welfare_fund_id'] = ft.welfare_fund_id

    entry, _ = write_ledger_entry(**kwargs)
    return entry
