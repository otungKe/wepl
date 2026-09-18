"""Per-context settlement reactions (ADR-0030 Slice B).

Each money-receiving context owns what happens to it when a payout settles or
fails, and registers that here instead of the settlement dispatcher switching on
``ft.context_type``. Registered from ``ContributionsConfig.ready()``.

Handlers receive the primitive ``context_id`` — never the FinancialTransaction —
so a target knows nothing about the ledger. Every handler is idempotent:
discovery is multi-source and delivery at-least-once (ADR-0028), so the same
settlement can arrive more than once.
"""
import logging

from django.utils import timezone

from apps.core.exceptions import TransitionError

from .settlement import register_settlement_target

logger = logging.getLogger(__name__)


# ── welfare claim ────────────────────────────────────────────────────────────

def _welfare_claim_settled(context_id: int, receipt: str = "") -> None:
    from .models import WelfareClaim
    from .services import _notify
    try:
        claim = WelfareClaim.objects.get(id=context_id)
        claim.transition_to(
            'DISBURSED',
            disbursed_at=timezone.now(),
            mpesa_receipt=receipt or None,
        )
        _notify(
            user=claim.claimant,
            notification_type='welfare_disbursed',
            title="M-Pesa payment sent!",
            message=(
                f"KES {claim.amount_requested:,.0f} has been sent to your M-Pesa."
                + (f" Receipt: {receipt}." if receipt else "")
            ),
        )
    except WelfareClaim.DoesNotExist:
        logger.warning("on_payout_settled: WelfareClaim %s not found", context_id)
    except TransitionError:
        logger.warning(
            "on_payout_settled: WelfareClaim %s already transitioned (idempotent)",
            context_id,
        )


def _welfare_claim_failed(context_id: int) -> None:
    from .models import WelfareClaim
    try:
        # Ledger funds are restored by reverse_financial_transaction;
        # reset the claim so it can be retried.
        claim = WelfareClaim.objects.get(id=context_id)
        claim.transition_to('PENDING')
    except (WelfareClaim.DoesNotExist, TransitionError):
        pass
    logger.error(
        "Welfare payout FAILED for claim %s — fund balance restored. Claim reset to PENDING.",
        context_id,
    )


# ── disbursement request ─────────────────────────────────────────────────────

def _disbursement_settled(context_id: int, receipt: str = "") -> None:
    from .models import DisbursementRequest
    from .services import _notify
    try:
        req = DisbursementRequest.objects.get(id=context_id)
        _notify(
            user=req.requested_by,
            notification_type='disbursement_sent',
            title="Disbursement sent!",
            message=(
                f"KES {req.amount} has been sent to {req.recipient_phone}."
                + (f" M-Pesa receipt: {receipt}." if receipt else "")
            ),
            contribution_id=req.contribution_id,
        )
    except DisbursementRequest.DoesNotExist:
        pass


def _disbursement_failed(context_id: int) -> None:
    from .models import DisbursementRequest
    try:
        req = DisbursementRequest.objects.get(id=context_id)
        req.transition_to('APPROVED')
    except (DisbursementRequest.DoesNotExist, TransitionError):
        pass
    logger.error(
        "Disbursement payout FAILED for request %s — pool balance has been restored. "
        "Admin must re-trigger the payout.",
        context_id,
    )


# ── emergency advance ────────────────────────────────────────────────────────

def _advance_settled(context_id: int, receipt: str = "") -> None:
    from .models import EmergencyAdvance
    from .services import _notify
    try:
        advance = EmergencyAdvance.objects.get(id=context_id)
        _notify(
            user=advance.borrower,
            notification_type='advance_sent',
            title="Advance sent!",
            message=(
                f"KES {advance.amount} has been sent to your M-Pesa."
                + (f" Receipt: {receipt}." if receipt else "")
            ),
            contribution_id=advance.contribution_id,
        )
    except EmergencyAdvance.DoesNotExist:
        pass


def _advance_failed(context_id: int) -> None:
    from .models import EmergencyAdvance
    try:
        advance = EmergencyAdvance.objects.get(id=context_id)
        advance.transition_to('APPROVED')
    except (EmergencyAdvance.DoesNotExist, TransitionError):
        pass
    logger.error(
        "Advance payout FAILED for advance %s — pool balance restored. "
        "Advance reset to APPROVED.",
        context_id,
    )


# ── standing order ───────────────────────────────────────────────────────────

def _standing_order_settled(context_id: int, receipt: str = "") -> None:
    logger.info(
        "Payout success for standing order context_id=%s receipt=%s",
        context_id, receipt,
    )


def register() -> None:
    """Register every contributions settlement target (called from AppConfig.ready)."""
    register_settlement_target(
        'welfare_claim',
        on_settled=_welfare_claim_settled, on_failed=_welfare_claim_failed)
    register_settlement_target(
        'disbursement_request',
        on_settled=_disbursement_settled, on_failed=_disbursement_failed)
    register_settlement_target(
        'emergency_advance',
        on_settled=_advance_settled, on_failed=_advance_failed)
    # Standing orders log on success and have no failure reset today.
    register_settlement_target(
        'standing_order', on_settled=_standing_order_settled)
