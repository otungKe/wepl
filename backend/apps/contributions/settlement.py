"""Business-domain reaction to a settled payout (ADR-0014, provider-agnostic).

When a payout ``FinancialTransaction`` settles, the linked domain object
(welfare claim, disbursement request, emergency advance, standing order) has to
advance and the member has to be notified. That routing is *contributions*
domain logic — it keys purely on ``ft.context_type``/``ft.context_id`` and knows
nothing about M-Pesa/Daraja. It used to live in ``apps/mpesa/views`` and
``apps/ledger/tasks``, so the rail app and the ledger owned business routing and
two higher layers reached in for it. It lives here now, and every settlement
path — the provider callback, the stale-payout sweep, and operator recovery —
calls these two entry points.

Idempotent: every domain transition tolerates being re-applied (the callback,
the sweep, and an operator can all try to finalise the same payout).
"""
import logging
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)


def on_collection_settled(*, payment_type, user, amount, receipt=None,
                          contribution_id=None, welfare_fund_id=None,
                          shares_fund_id=None, advance_id=None,
                          idempotency_seed=None) -> None:
    """Route a settled pay-in (collection) to the business service that credits
    it. Provider-agnostic: takes normalised primitives, not a rail model, so any
    collection rail (M-Pesa STK today, card/bank later) settles through one door.

    ``idempotency_seed`` is a caller-supplied fallback token (e.g. the rail's
    checkout id) used to build a stable idempotency key when no receipt is present.
    """
    from .services import (
        ContributionService, EmergencyAdvanceService, SharesService, WelfareService,
    )

    if payment_type == "welfare" and welfare_fund_id:
        WelfareService.contribute_to_welfare(
            welfare_fund_id, user, amount, mpesa_receipt=receipt)
    elif payment_type == "shares" and shares_fund_id:
        SharesService.purchase(
            user, shares_fund_id, amount,
            mpesa_receipt=receipt, idempotency_key=idempotency_seed)
    elif payment_type == "advance_repayment" and advance_id:
        EmergencyAdvanceService.repay(
            advance_id, user, amount, mpesa_receipt=receipt)
    else:
        idem = f"contrib-stk-{receipt or idempotency_seed}"
        ContributionService.contribute(
            user, contribution_id, amount,
            mpesa_receipt=receipt, idempotency_key=idem)


# ── Settlement-target registry (ADR-0030 Slice B) ─────────────────────────────
# A settled payout has to reach *its* domain object. That routing used to be a
# hardcoded if/elif over ``ft.context_type`` living here, which meant the
# dispatcher had to know every money-receiving context by name. Each context now
# owns its own reaction and registers it (from AppConfig.ready(), the same
# discipline as policies / exception renderers / inline consumers, ADR-0031), so
# adding or moving a context never edits this file.
#
# Handlers take the primitive ``context_id`` — never the FT — so a target knows
# nothing about the ledger. That is what lets the workflow dimension leave FT
# entirely in a later slice: only the lookup below has to change.
@dataclass(frozen=True)
class SettlementTarget:
    context_type: str
    on_settled: Callable[[int, str], None] | None = None
    on_failed: Callable[[int], None] | None = None


_TARGETS: dict[str, SettlementTarget] = {}


def register_settlement_target(context_type: str, *,
                               on_settled: Callable[[int, str], None] | None = None,
                               on_failed: Callable[[int], None] | None = None) -> None:
    """Register a context's settlement reactions. Handlers must be idempotent —
    discovery is multi-source and delivery at-least-once (ADR-0028)."""
    if context_type in _TARGETS:
        logger.warning("Settlement target for '%s' is being overwritten.", context_type)
    _TARGETS[context_type] = SettlementTarget(context_type, on_settled, on_failed)


def settlement_target_for(context_type: str) -> SettlementTarget | None:
    return _TARGETS.get(context_type)


def on_payout_settled(ft, receipt: str = "") -> None:
    """Advance the linked domain object and notify the member after a payout
    succeeds. Dispatches on ``ft.context_type`` via the target registry; a no-op
    when the FT carries no context (e.g. a manual adjustment) or the context type
    has no registered target."""
    if not ft.context_type or not ft.context_id:
        return

    target = _TARGETS.get(ft.context_type)
    if target is None or target.on_settled is None:
        logger.debug("on_payout_settled: no target for context_type %r", ft.context_type)
        return
    target.on_settled(ft.context_id, receipt)


def on_payout_failed(ft) -> None:
    """Reset the linked domain object to a retryable state after a payout fails
    (the reserved funds are restored separately by the ledger reversal).
    Dispatches via the target registry; a no-op when the FT carries no context.

    A target's failure is logged and swallowed, preserving the long-standing
    guarantee that a domain-update error here can never break the money path."""
    if not ft.context_type or not ft.context_id:
        return

    target = _TARGETS.get(ft.context_type)
    if target is None or target.on_failed is None:
        logger.debug("on_payout_failed: no target for context_type %r", ft.context_type)
        return

    try:
        target.on_failed(ft.context_id)
    except Exception:
        logger.exception(
            "on_payout_failed: error updating context %s/%s",
            ft.context_type, ft.context_id,
        )


# ── Rail registration (ADR-0033) ─────────────────────────────────────────────
# ``apps.mpesa`` owns the rail records and nothing above them, so it asks who
# decides what a settled payment means rather than importing the answer. Both
# handlers resolve their target at call time so a test can patch either one.

def _collection_settled(**kwargs) -> None:
    on_collection_settled(**kwargs)


def _paybill_payin(**kwargs) -> dict:
    from .services import ContributionService
    return ContributionService.credit_paybill_payin(**kwargs)


def register() -> None:
    """Hand the M-Pesa rail the two domain decisions it must not import."""
    from apps.mpesa.settlement import (
        register_collection_settled, register_paybill_resolver,
    )
    register_collection_settled(_collection_settled)
    register_paybill_resolver(_paybill_payin)
