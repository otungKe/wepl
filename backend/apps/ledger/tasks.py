"""
Ledger Celery tasks — the financial execution engine.

All outgoing M-Pesa B2C payments are dispatched through here, so that:
  - DB transactions are never held open while HTTP calls are in-flight
  - State transitions are atomic (UPDATE WHERE state = current)
  - Retries are idempotent via FinancialTransaction.idempotency_key
  - Failures write reversal ledger entries so pool balances stay correct
  - The B2C async result (from B2CResultView) handles SUCCESS/FAILED resolution

P1-07 fix: _handle_payout_failure is now called ONLY from on_failure (after
all retries are exhausted), not from the retry path.  The prior code called it
before raise self.retry(), which transitioned FT → FAILED and caused the retry
guard (if ft.state == FAILED: return) to fire on every subsequent attempt —
effectively zero retries.

P1-07 fix: retries resume from PROCESSING state (set on first attempt).
The task now skips the PENDING→PROCESSING transition when ft.state is already
PROCESSING, so retry attempts proceed to the B2C call without a TransitionError.
"""
import logging

from celery import shared_task

from apps.core.exceptions import TransitionError

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue='financial',
    acks_late=True,
)
def execute_b2c_payout(self, fin_transaction_id: int) -> str:
    """
    Fire a Safaricom B2C payment for an outgoing FinancialTransaction.

    Flow:
      1. Load FT — exit early if already SUCCESS/FAILED or already dispatched.
      2. Transition PENDING → PROCESSING (skip if already PROCESSING from a retry).
      3. Call MpesaService.b2c_payment() — OUTSIDE any DB transaction.
      4. Store ConversationID on FT; leave state as PROCESSING.
      5. B2CResultView handles the async callback → SUCCESS or FAILED.

    On transient exception:
      - Log and raise self.retry() — Celery will retry up to max_retries times.
      - _handle_payout_failure is NOT called here; it runs in on_failure after
        all retries are exhausted.
    """
    from apps.ledger.models import FinancialTransaction
    from apps.mpesa.services import MpesaService

    try:
        ft = FinancialTransaction.objects.get(id=fin_transaction_id)
    except FinancialTransaction.DoesNotExist:
        logger.error("execute_b2c_payout: FT %s not found", fin_transaction_id)
        return "not_found"

    # Guard: do nothing if already in a terminal or post-dispatch state
    if ft.state == FinancialTransaction.State.SUCCESS:
        return "already_succeeded"
    if ft.state == FinancialTransaction.State.FAILED:
        return "already_failed"
    if ft.mpesa_conversation_id:
        # B2C was already dispatched — waiting for callback
        logger.info(
            "execute_b2c_payout: FT %s already dispatched (conv=%s)",
            ft.id, ft.mpesa_conversation_id,
        )
        return "b2c_already_sent"

    # Transition PENDING → PROCESSING on first attempt.
    # On retry attempts the FT is already PROCESSING — skip the transition and
    # proceed directly to the B2C call.
    if ft.state == FinancialTransaction.State.PENDING:
        try:
            ft.transition_to(FinancialTransaction.State.PROCESSING)
        except TransitionError as exc:
            logger.warning(
                "execute_b2c_payout: FT %s transition conflict: %s", ft.id, exc
            )
            return "transition_conflict"
    elif ft.state != FinancialTransaction.State.PROCESSING:
        logger.warning(
            "execute_b2c_payout: FT %s in unexpected state %s — aborting",
            ft.id, ft.state,
        )
        return "unexpected_state"

    reference = f"WEPL-{ft.op_type[:4].upper()}-{ft.id}"
    remarks   = f"{ft.get_op_type_display()} #{ft.id}"

    try:
        result = MpesaService.b2c_payment(
            phone_number=ft.recipient_phone,
            amount=ft.amount,
            reference=reference[:100],
            remarks=remarks[:100],
        )
    except Exception as exc:
        attempt = self.request.retries + 1
        logger.exception(
            "execute_b2c_payout: B2C HTTP call failed for FT %s (attempt %d/%d)",
            ft.id, attempt, self.max_retries + 1,
        )
        if self.request.retries >= self.max_retries:
            # All retries exhausted — write reversal and mark terminal failure.
            logger.error(
                "execute_b2c_payout: all retries exhausted for FT %s — marking FAILED",
                ft.id,
            )
            _handle_payout_failure(ft, str(exc))
            return "all_retries_exhausted"
        raise self.retry(exc=exc)

    conversation_id = (
        result.get('ConversationID') or
        result.get('OriginatorConversationID') or ''
    )
    if not conversation_id:
        err = f"No ConversationID in B2C response: {result}"
        logger.error("execute_b2c_payout: FT %s — %s", ft.id, err)
        _handle_payout_failure(ft, err)
        return "no_conversation_id"

    FinancialTransaction.objects.filter(pk=ft.pk).update(
        mpesa_conversation_id=conversation_id
    )
    logger.info(
        "execute_b2c_payout: FT %s dispatched — conversation_id=%s", ft.id, conversation_id
    )
    return f"dispatched:{conversation_id}"


@shared_task(queue='financial')
def recover_stale_processing_transactions() -> int:
    """
    Find FinancialTransactions stuck in PROCESSING for > 15 minutes and log them.
    Runs every 30 minutes via Celery Beat.

    TODO: extend to query Safaricom transaction status API and auto-resolve.
    For now: logs a critical alert so ops can investigate.
    """
    from datetime import timedelta
    from django.utils import timezone
    from apps.ledger.models import FinancialTransaction

    cutoff = timezone.now() - timedelta(minutes=15)
    stale = FinancialTransaction.objects.filter(
        state=FinancialTransaction.State.PROCESSING,
        updated_at__lt=cutoff,
    )

    count = stale.count()
    for ft in stale:
        logger.critical(
            "STALE PROCESSING TRANSACTION: FT-%s op=%s amount=%s "
            "context=%s/%s conversation_id=%s — manual review or Safaricom status query required.",
            ft.id, ft.op_type, ft.amount,
            ft.context_type, ft.context_id,
            ft.mpesa_conversation_id,
        )

    if count:
        logger.critical(
            "recover_stale_processing_transactions: %d stale transaction(s) detected.", count
        )
    else:
        logger.info("recover_stale_processing_transactions: no stale transactions.")

    return count


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _handle_payout_failure(ft, reason: str) -> None:
    """
    On B2C failure (called from on_failure after all retries, or for hard errors):
      1. Write a REVERSAL_CREDIT to restore the reserved pool funds.
      2. Transition FT to FAILED.
      3. Update the linked domain object so admins/users can see the failure
         and retry if appropriate.
    """
    from apps.ledger.models import FinancialTransaction
    from apps.ledger.writer import write_reversal_credit

    try:
        write_reversal_credit(ft, note=reason[:500])
    except Exception:
        logger.exception("_handle_payout_failure: could not write reversal for FT %s", ft.id)

    try:
        ft.transition_to(FinancialTransaction.State.FAILED, failure_reason=reason[:500])
    except TransitionError:
        pass  # already transitioned by another path

    _update_context_on_failure(ft)


def _update_context_on_failure(ft) -> None:
    """Reset the linked domain object to a retryable state after a payout failure."""
    if not ft.context_type or not ft.context_id:
        return

    try:
        if ft.context_type == 'disbursement_request':
            from apps.contributions.models import DisbursementRequest
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
            from django.db.models import F
            from apps.contributions.models import WelfareClaim, WelfareFund
            try:
                claim = WelfareClaim.objects.get(id=ft.context_id)
                claim.transition_to('PENDING')
                # Restore the mutable WelfareFund.balance field.
                # write_reversal_credit already restores the immutable ledger;
                # this keeps the mutable field in sync so submit_claim balance
                # guards work correctly.
                WelfareFund.objects.filter(pk=claim.fund_id).update(
                    balance=F('balance') + claim.amount_requested
                )
            except (WelfareClaim.DoesNotExist, TransitionError):
                pass
            logger.error(
                "Welfare payout FAILED for claim %s — fund balance restored. Claim reset to PENDING.",
                ft.context_id,
            )

        elif ft.context_type == 'emergency_advance':
            from apps.contributions.models import EmergencyAdvance
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
            "_update_context_on_failure: error updating context %s/%s",
            ft.context_type, ft.context_id,
        )
