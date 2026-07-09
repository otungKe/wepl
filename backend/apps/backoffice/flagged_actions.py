"""
Registry of maker-checked (flagged) ops actions — OP-3 Part 2.

Each flagged action declares the capability required to *request* it, how to
execute it once approved, and a human summary for the approvals inbox. Registered
from ``BackofficeConfig.ready()``. The first flagged action is a money reversal
(OP-1's deferred destructive lever); LimitRule changes, control-override
issuance, and staff role changes plug in here the same way.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError

from .approvals import FlaggedAction, register

ACTION_REVERSAL = "finops.reverse"


def _execute_reversal(params: dict, *, actor_label: str = "") -> dict:
    from apps.ledger.models import FinancialTransaction
    from apps.payments.ops import PaymentOpsService
    try:
        ft = FinancialTransaction.objects.get(pk=params["ft_id"])
    except FinancialTransaction.DoesNotExist:
        raise ValidationError("The movement to reverse no longer exists.")
    return PaymentOpsService.reverse(ft, reason=params.get("reason", ""), actor_label=actor_label)


def _summary_reversal(params: dict) -> str:
    return f"Reverse movement #{params.get('ft_id')} — KES {params.get('amount', '?')}"


def register_all() -> None:
    register(ACTION_REVERSAL, FlaggedAction(
        capability="finops.reverse",
        execute=_execute_reversal,
        summary=_summary_reversal,
        target_type="financial_transaction",
    ))
