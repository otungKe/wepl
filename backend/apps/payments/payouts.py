"""
Payout orchestration — the rail-facing execution engine for outgoing money.

This lived in ``apps/ledger/tasks.py`` until #159. The ledger is the book of
record: it *posts journals* and knows nothing about a rail. Dispatching a
payout, polling the rail for a stalled one and finalising a failure are
orchestration, so they belong here, above the ledger and behind the
``PaymentProvider`` port (ADR-0005). The ledger is left with pure book-keeping.

All outgoing payments are dispatched through here, so that:
  - DB transactions are never held open while HTTP calls are in-flight
  - State transitions are atomic (UPDATE WHERE state = current)
  - Retries are idempotent via FinancialTransaction.idempotency_key
  - Failures emit a durable payment.failed event (ADR-0028); the inline
    settlement consumer posts the reversing journal so pool balances stay correct
  - The async payout result (from B2CResultView) handles SUCCESS/FAILED resolution

P1-07 fix: _handle_payout_failure is now called ONLY from on_failure (after
all retries are exhausted), not from the retry path.  The prior code called it
before raise self.retry(), which transitioned FT → FAILED and caused the retry
guard (if ft.state == FAILED: return) to fire on every subsequent attempt —
effectively zero retries.

P1-07 fix: retries resume from PROCESSING state (set on first attempt).
The task now skips the PENDING→PROCESSING transition when ft.state is already
PROCESSING, so retry attempts proceed to the rail call without a TransitionError.
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
def execute_payout(self, fin_transaction_id: int) -> str:
    """
    Fire a rail payout for an outgoing FinancialTransaction.

    Flow:
      1. Load FT — exit early if already SUCCESS/FAILED or already dispatched.
      2. Transition PENDING → PROCESSING (skip if already PROCESSING from a retry).
      3. Call the provider's initiate_payout() — OUTSIDE any DB transaction.
      4. Store the provider reference on the FT; leave state as PROCESSING.
      5. B2CResultView handles the async callback → SUCCESS or FAILED.

    On transient exception:
      - Log and raise self.retry() — Celery will retry up to max_retries times.
      - _handle_payout_failure is NOT called here; it runs in on_failure after
        all retries are exhausted.
    """
    from apps.ledger.models import FinancialTransaction

    try:
        ft = FinancialTransaction.objects.get(id=fin_transaction_id)
    except FinancialTransaction.DoesNotExist:
        logger.error("execute_payout: FT %s not found", fin_transaction_id)
        return "not_found"

    # Guard: do nothing if already in a terminal or post-dispatch state
    if ft.state == FinancialTransaction.State.SUCCESS:
        return "already_succeeded"
    if ft.state == FinancialTransaction.State.FAILED:
        return "already_failed"
    if ft.mpesa_conversation_id:
        # The payout was already dispatched — waiting for callback
        logger.info(
            "execute_payout: FT %s already dispatched (ref=%s)",
            ft.id, ft.mpesa_conversation_id,
        )
        return "b2c_already_sent"

    # Transition PENDING → PROCESSING on first attempt.
    # On retry attempts the FT is already PROCESSING — skip the transition and
    # proceed directly to the rail call.
    if ft.state == FinancialTransaction.State.PENDING:
        try:
            ft.transition_to(FinancialTransaction.State.PROCESSING)
        except TransitionError as exc:
            logger.warning(
                "execute_payout: FT %s transition conflict: %s", ft.id, exc
            )
            return "transition_conflict"
    elif ft.state != FinancialTransaction.State.PROCESSING:
        logger.warning(
            "execute_payout: FT %s in unexpected state %s — aborting",
            ft.id, ft.state,
        )
        return "unexpected_state"

    reference = f"WEPL-{ft.op_type[:4].upper()}-{ft.id}"
    remarks   = f"{ft.get_op_type_display()} #{ft.id}"

    try:
        from apps.payments.providers.registry import get_provider
        from apps.ledger.money import Money
        result = get_provider().initiate_payout(
            phone=ft.recipient_phone,
            amount=Money(str(ft.amount)),
            reference=reference[:100],
            remarks=remarks[:100],
        )
    except Exception as exc:
        attempt = self.request.retries + 1
        logger.exception(
            "execute_payout: rail call failed for FT %s (attempt %d/%d)",
            ft.id, attempt, self.max_retries + 1,
        )
        if self.request.retries >= self.max_retries:
            # All retries exhausted — write reversal and mark terminal failure.
            logger.error(
                "execute_payout: all retries exhausted for FT %s — marking FAILED",
                ft.id,
            )
            _handle_payout_failure(ft, str(exc))
            return "all_retries_exhausted"
        raise self.retry(exc=exc)

    provider_ref = result.provider_ref
    if not result.accepted or not provider_ref:
        err = f"B2C payout not accepted by provider: {result.raw}"
        logger.error("execute_payout: FT %s — %s", ft.id, err)
        _handle_payout_failure(ft, err)
        return "no_conversation_id"

    FinancialTransaction.objects.filter(pk=ft.pk).update(
        mpesa_conversation_id=provider_ref
    )

    # Provider-agnostic payment aggregate (ADR-0014) — best-effort, linked to the FT.
    try:
        from apps.payments.providers.registry import get_provider
        from apps.payments.services import PaymentService
        from apps.payments.models import PaymentIntent
        PaymentService.record_initiation(
            provider=get_provider().name,
            direction=PaymentIntent.Direction.PAYOUT,
            amount=ft.amount,
            idempotency_key=f"pi-payout-{ft.id}",
            provider_ref=provider_ref,
            financial_transaction=ft,
            op_type=ft.op_type,
            tenant_id=ft.tenant_id,
        )
    except Exception:
        logger.exception("record_initiation (payout) failed for FT %s", ft.id)

    logger.info(
        "execute_payout: FT %s dispatched — provider_ref=%s", ft.id, provider_ref
    )
    return f"dispatched:{provider_ref}"


@shared_task(queue='financial')
def recover_stale_processing_transactions() -> dict:
    """
    Two-tier recovery for FinancialTransactions stuck in PROCESSING.

    Tier 1 — warn (> 15 min):  CRITICAL log so ops can investigate immediately
              while the rail's callback might still arrive.

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
            # ── Tier 2: query the rail, then auto-recover ─────────────────────
            # Try the rail's status facility first so we know the real outcome.
            # If the query confirms SUCCESS we record it correctly rather than
            # writing a false reversal.
            rail_state = _query_payout_status(ft)

            if rail_state == "SUCCESS":
                logger.info(
                    "STALE-RECOVER: FT-%s confirmed SUCCESS by the rail — "
                    "transitioning to SUCCESS without reversal.",
                    ft.id,
                )
                try:
                    from django.db import transaction

                    from apps.core.events import emit_event
                    receipt = ft.mpesa_receipt or ""
                    # Discovery → one durable settlement event (ADR-0028); the
                    # inline settlement consumer propagates it. Atomic with the
                    # transition (same posture as the B2C callback), so a won
                    # transition always carries its event.
                    with transaction.atomic():
                        ft.transition_to(FinancialTransaction.State.SUCCESS)
                        emit_event(
                            'payment.settled',
                            aggregate_key=f'ft:{ft.id}',
                            dedup_key=f'payment.settled:ft={ft.id}',
                            body={'ft_id': ft.id, 'receipt': receipt},
                        )
                    recovered += 1
                except Exception:
                    logger.exception("STALE-RECOVER: success-transition failed for FT-%s", ft.id)

            else:
                # FAILED, UNKNOWN, or query itself failed — treat as failed.
                logger.error(
                    "STALE-RECOVER: FT-%s op=%s amount=%s context=%s/%s "
                    "provider_ref=%s stuck > 60 min (rail_state=%s) — "
                    "forcing FAILED and writing reversal.",
                    ft.id, ft.op_type, ft.amount,
                    ft.context_type, ft.context_id,
                    ft.mpesa_conversation_id, rail_state,
                )
                try:
                    _handle_payout_failure(
                        ft,
                        f"Auto-recovered after 60 min in PROCESSING "
                        f"(rail_state={rail_state}, "
                        f"provider_ref={ft.mpesa_conversation_id}).",
                    )
                    recovered += 1
                except Exception:
                    logger.exception("STALE-RECOVER: failed to auto-recover FT-%s", ft.id)
        else:
            # ── Tier 1: warn only (callback might still arrive) ───────────────
            logger.critical(
                "STALE-WARN: FT-%s op=%s amount=%s context=%s/%s "
                "provider_ref=%s stuck > 15 min — awaiting rail callback.",
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
# Legacy task names (deploy window)
# ---------------------------------------------------------------------------
# Messages queued under the old ``apps.ledger.tasks.*`` names — in-flight work
# and any stale django-celery-beat row — still resolve after this move. The
# shims re-queue onto the new names; the tasks' own guards make that safe.

@shared_task(name='apps.ledger.tasks.execute_b2c_payout', queue='financial')
def _legacy_execute_b2c_payout(fin_transaction_id: int) -> str:
    logger.info(
        "execute_b2c_payout: legacy task name — re-queueing FT %s as execute_payout",
        fin_transaction_id,
    )
    execute_payout.delay(fin_transaction_id)
    return "requeued"


@shared_task(name='apps.ledger.tasks.recover_stale_processing_transactions',
             queue='financial')
def _legacy_recover_stale_processing_transactions() -> dict:
    return recover_stale_processing_transactions()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _query_payout_status(ft) -> str:
    """
    Ask the rail for a stuck payout's outcome, through the PaymentProvider port.
    Returns "SUCCESS", "FAILED", or "UNKNOWN" (on error or inconclusive result).

    M-Pesa answers asynchronously — its TransactionStatusQuery only re-fires the
    result callback — so the adapter reports ``unknown`` and the callback updates
    the FT when it arrives. Rails that answer inline map straight through.
    """
    if not ft.mpesa_conversation_id:
        return "UNKNOWN"

    try:
        from apps.payments.providers.registry import get_provider

        result = get_provider().request_payout_result(
            provider_ref=ft.mpesa_conversation_id,
            remarks=f"Status query for FT-{ft.id}",
        )
    except Exception as exc:
        logger.warning(
            "_query_payout_status: FT-%s query failed (%s) — treating as UNKNOWN",
            ft.id, exc,
        )
        return "UNKNOWN"

    return {'success': "SUCCESS", 'failed': "FAILED"}.get(result.state, "UNKNOWN")


def _handle_payout_failure(ft, reason: str) -> None:
    """
    On payout failure (called from on_failure after all retries, or for hard errors):
    transition FT to FAILED and, atomically, emit one durable ``payment.failed``
    event (ADR-0028). The inline settlement consumer then restores the reserved
    pool funds (ledger reversal) and resets the linked domain object so admins /
    users can see the failure and retry if appropriate.

    Emitting inside the transition's transaction means a won transition always
    carries its event (no lost reversal); a lost race (already terminal) is a
    no-op — the winning witness already emitted.
    """
    from django.db import transaction

    from apps.core.events import emit_event
    from apps.ledger.models import FinancialTransaction

    try:
        with transaction.atomic():
            ft.transition_to(
                FinancialTransaction.State.FAILED, failure_reason=reason[:500])
            emit_event(
                'payment.failed',
                aggregate_key=f'ft:{ft.id}',
                dedup_key=f'payment.failed:ft={ft.id}',
                body={'ft_id': ft.id, 'reason': reason[:500]},
            )
    except TransitionError:
        pass  # already finalised by another path (idempotent)
