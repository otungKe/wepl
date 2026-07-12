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

from django.utils import timezone

from apps.core.exceptions import TransitionError

logger = logging.getLogger(__name__)


def on_payout_settled(ft, receipt: str = "") -> None:
    """Advance the linked domain object and notify the member after a payout
    succeeds. Routes on ``ft.context_type``; a no-op when the FT carries no
    context (e.g. a manual adjustment)."""
    from .services import _notify

    if not ft.context_type or not ft.context_id:
        return

    if ft.context_type == 'welfare_claim':
        from .models import WelfareClaim
        try:
            claim = WelfareClaim.objects.get(id=ft.context_id)
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
            logger.warning("on_payout_settled: WelfareClaim %s not found", ft.context_id)
        except TransitionError:
            logger.warning(
                "on_payout_settled: WelfareClaim %s already transitioned (idempotent)",
                ft.context_id,
            )

    elif ft.context_type == 'disbursement_request':
        from .models import DisbursementRequest
        try:
            req = DisbursementRequest.objects.get(id=ft.context_id)
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

    elif ft.context_type == 'emergency_advance':
        from .models import EmergencyAdvance
        try:
            advance = EmergencyAdvance.objects.get(id=ft.context_id)
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

    elif ft.context_type == 'standing_order':
        logger.info(
            "Payout success for standing order context_id=%s receipt=%s",
            ft.context_id, receipt,
        )


def on_payout_failed(ft) -> None:
    """Reset the linked domain object to a retryable state after a payout fails
    (the reserved funds are restored separately by the ledger reversal). Routes on
    ``ft.context_type``; a no-op when the FT carries no context."""
    if not ft.context_type or not ft.context_id:
        return

    try:
        if ft.context_type == 'disbursement_request':
            from .models import DisbursementRequest
            try:
                req = DisbursementRequest.objects.get(id=ft.context_id)
                req.transition_to('APPROVED')
            except (DisbursementRequest.DoesNotExist, TransitionError):
                pass
            logger.error(
                "Disbursement payout FAILED for request %s — pool balance has been restored. "
                "Admin must re-trigger the payout.",
                ft.context_id,
            )

        elif ft.context_type == 'welfare_claim':
            from .models import WelfareClaim
            try:
                # Ledger funds are restored by reverse_financial_transaction;
                # reset the claim so it can be retried.
                claim = WelfareClaim.objects.get(id=ft.context_id)
                claim.transition_to('PENDING')
            except (WelfareClaim.DoesNotExist, TransitionError):
                pass
            logger.error(
                "Welfare payout FAILED for claim %s — fund balance restored. Claim reset to PENDING.",
                ft.context_id,
            )

        elif ft.context_type == 'emergency_advance':
            from .models import EmergencyAdvance
            try:
                advance = EmergencyAdvance.objects.get(id=ft.context_id)
                advance.transition_to('APPROVED')
            except (EmergencyAdvance.DoesNotExist, TransitionError):
                pass
            logger.error(
                "Advance payout FAILED for advance %s — pool balance restored. "
                "Advance reset to APPROVED.",
                ft.context_id,
            )

    except Exception:
        logger.exception(
            "on_payout_failed: error updating context %s/%s",
            ft.context_type, ft.context_id,
        )
