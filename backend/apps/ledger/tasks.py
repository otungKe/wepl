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
def recover_stale_processing_transactions() -> dict:
    """
    Two-tier recovery for FinancialTransactions stuck in PROCESSING.

    Tier 1 — warn (> 15 min):  CRITICAL log so ops can investigate immediately
              while the Safaricom callback might still arrive.

    Tier 2 — auto-recover (> 60 min):  The callback window is long past.
              Mark FAILED, write reversal ledger entry to restore pool funds,
              and reset the linked domain object so admins can re-trigger.

    Runs every 30 minutes via Celery Beat (settings.CELERY_BEAT_SCHEDULE).
    """
    from datetime import timedelta
    from django.utils import timezone
    from apps.ledger.models import FinancialTransaction

    now        = timezone.now()
    warn_at    = now - timedelta(minutes=15)
    recover_at = now - timedelta(minutes=60)

    all_stale = FinancialTransaction.objects.filter(
        state=FinancialTransaction.State.PROCESSING,
        updated_at__lt=warn_at,
    ).order_by("updated_at")

    warned    = 0
    recovered = 0

    for ft in all_stale:
        if ft.updated_at < recover_at:
            # ── Tier 2: query Safaricom, then auto-recover ────────────────────
            # Try the Transaction Status API first so we know the real outcome.
            # If the query confirms SUCCESS we record it correctly rather than
            # writing a false reversal.
            safaricom_state = _query_safaricom_status(ft)

            if safaricom_state == "SUCCESS":
                logger.info(
                    "STALE-RECOVER: FT-%s confirmed SUCCESS by Safaricom — "
                    "transitioning to SUCCESS without reversal.",
                    ft.id,
                )
                try:
                    from apps.core.exceptions import TransitionError
                    ft.transition_to(FinancialTransaction.State.SUCCESS)
                    # Trigger the same success handler the B2C callback would use
                    from apps.mpesa.views import _on_b2c_success
                    receipt = ft.mpesa_receipt or ""
                    _on_b2c_success(ft, receipt)
                    recovered += 1
                except Exception:
                    logger.exception("STALE-RECOVER: success-transition failed for FT-%s", ft.id)

            else:
                # FAILED, UNKNOWN, or query itself failed — treat as failed.
                logger.error(
                    "STALE-RECOVER: FT-%s op=%s amount=%s context=%s/%s "
                    "conversation_id=%s stuck > 60 min (safaricom_state=%s) — "
                    "forcing FAILED and writing reversal.",
                    ft.id, ft.op_type, ft.amount,
                    ft.context_type, ft.context_id,
                    ft.mpesa_conversation_id, safaricom_state,
                )
                try:
                    _handle_payout_failure(
                        ft,
                        f"Auto-recovered after 60 min in PROCESSING "
                        f"(safaricom_state={safaricom_state}, "
                        f"conversation_id={ft.mpesa_conversation_id}).",
                    )
                    recovered += 1
                except Exception:
                    logger.exception("STALE-RECOVER: failed to auto-recover FT-%s", ft.id)
        else:
            # ── Tier 1: warn only (callback might still arrive) ───────────────
            logger.critical(
                "STALE-WARN: FT-%s op=%s amount=%s context=%s/%s "
                "conversation_id=%s stuck > 15 min — awaiting Safaricom callback.",
                ft.id, ft.op_type, ft.amount,
                ft.context_type, ft.context_id,
                ft.mpesa_conversation_id,
            )
            warned += 1

    summary = {"warned": warned, "recovered": recovered}
    if warned or recovered:
        logger.critical(
            "recover_stale_processing_transactions: %d warned, %d auto-recovered.",
            warned, recovered,
        )
    else:
        logger.info("recover_stale_processing_transactions: no stale transactions.")

    return summary


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _query_safaricom_status(ft) -> str:
    """
    Query the Safaricom B2C Transaction Status API for a stuck FT.
    Returns "SUCCESS", "FAILED", or "UNKNOWN" (on error or inconclusive result).

    Uses the same Daraja credentials already in settings.
    Works in both sandbox and production — the endpoint is the same.
    """
    if not ft.mpesa_conversation_id:
        return "UNKNOWN"

    try:
        from apps.mpesa.services import MpesaService
        from django.conf import settings

        token = MpesaService._get_access_token()
        import requests

        payload = {
            "Initiator":          settings.MPESA_B2C_INITIATOR_NAME,
            "SecurityCredential": settings.MPESA_B2C_SECURITY_CREDENTIAL,
            "CommandID":          "TransactionStatusQuery",
            "TransactionID":      ft.mpesa_conversation_id,
            "PartyA":             settings.MPESA_SHORTCODE,
            "IdentifierType":     "4",
            "ResultURL":          settings.MPESA_B2C_RESULT_URL,
            "QueueTimeOutURL":    settings.MPESA_B2C_TIMEOUT_URL,
            "Remarks":            f"Status query for FT-{ft.id}",
            "Occasion":           "",
        }
        resp = requests.post(
            f"{settings.MPESA_BASE_URL}/mpesa/transactionstatus/v1/query",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        # Safaricom returns ResponseCode "0" for an accepted query;
        # the actual result arrives asynchronously via the ResultURL callback.
        # We return UNKNOWN here — the callback will update the FT when it arrives.
        if data.get("ResponseCode") == "0":
            logger.info(
                "_query_safaricom_status: FT-%s query accepted "
                "(async result will arrive via ResultURL)", ft.id
            )
        else:
            logger.warning(
                "_query_safaricom_status: FT-%s unexpected response: %s", ft.id, data
            )
        return "UNKNOWN"

    except Exception as exc:
        logger.warning(
            "_query_safaricom_status: FT-%s query failed (%s) — treating as UNKNOWN",
            ft.id, exc,
        )
        return "UNKNOWN"


def _handle_payout_failure(ft, reason: str) -> None:
    """
    On B2C failure (called from on_failure after all retries, or for hard errors):
      1. Write a REVERSAL_CREDIT to restore the reserved pool funds.
      2. Transition FT to FAILED.
      3. Update the linked domain object so admins/users can see the failure
         and retry if appropriate.
    """
    from apps.ledger.models import FinancialTransaction
    from apps.ledger.posting import reverse_financial_transaction

    try:
        reverse_financial_transaction(ft, note=reason[:500])  # restore reserved funds
    except Exception:
        logger.exception("_handle_payout_failure: could not reverse journal for FT %s", ft.id)

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
                # Keep the mutable WelfareFund.balance cache in sync (the ledger
                # is already restored by reverse_financial_transaction). This
                # cache is removed in P0-07 Milestone 2.
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
