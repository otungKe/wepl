"""
M-Pesa rail-side processing of a settled STK payment.

Everything here reads ``MpesaSTKRequest`` — this app's own record — and hands the
normalised result to the domain through ``apps.mpesa.settlement``. What a settled
payment *means* is not the rail's business, so the rail does not import the apps
that decide it (ADR-0033).

``process_stk_sync`` is the synchronous path the callback endpoint takes;
``process_stk_payment`` is the retryable Celery fallback behind it.
"""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    queue='payments',
    acks_late=True,
)
def process_stk_payment(self, stk_request_id: int) -> str:
    """
    Process the domain side-effects of a successful M-Pesa STK payment.

    Called via on_commit after the STK callback endpoint atomically claims the
    callback row. Retries up to 3 times on any transient failure (DB, network,
    constraint).

    The STKRequest already has status=SUCCESS and mpesa_receipt set — this task
    only creates the contribution/welfare/shares ledger records.
    """
    from .models import MpesaSTKRequest

    try:
        stk = MpesaSTKRequest.objects.select_related(
            'user', 'contribution', 'welfare_fund', 'shares_fund', 'advance'
        ).get(id=stk_request_id)
    except MpesaSTKRequest.DoesNotExist:
        logger.error("process_stk_payment: STKRequest %s not found", stk_request_id)
        return "not_found"

    try:
        # Read the rail model; delegate the business routing to the domain seam
        # (the same door the synchronous callback path uses).
        from .settlement import run_collection_settled
        run_collection_settled(
            payment_type=stk.payment_type, user=stk.user, amount=stk.amount,
            receipt=stk.mpesa_receipt, contribution_id=stk.contribution_id,
            welfare_fund_id=stk.welfare_fund_id, shares_fund_id=stk.shares_fund_id,
            advance_id=stk.advance_id, idempotency_seed=stk.checkout_request_id,
        )

    except Exception as exc:
        logger.exception(
            "process_stk_payment: reconcile failed for STKRequest %s (attempt %d/%d)",
            stk_request_id,
            self.request.retries + 1,
            self.max_retries + 1,
        )
        raise self.retry(exc=exc)

    logger.info(
        "process_stk_payment: STKRequest %s processed — type=%s receipt=%s",
        stk_request_id, stk.payment_type, stk.mpesa_receipt,
    )
    return "processed"


def enqueue_stk_processing(stk_id: int) -> None:
    """Hand the STK request to the Celery fallback.

    Best-effort: a broker outage must not 500 the callback handler. The STK
    request is committed, so the stuck-transaction sweep / ops retry lever pick it
    up; Safaricom also re-delivers the callback if we don't 200 promptly."""
    from apps.core.dispatch import safe_enqueue
    safe_enqueue(process_stk_payment, stk_id, critical=True, options={'queue': 'payments'})


def process_stk_sync(stk_id: int) -> None:
    """
    Process a settled STK payment synchronously, after the DB transaction commits.

    Running synchronously here (rather than via Celery) means the contribution
    balance, transaction record, and activity log are all written before the
    Safaricom webhook response is returned — so the mobile sees consistent data
    the first time it polls after payment confirmation.

    If synchronous processing raises any exception (rare — all operations are DB
    writes), we fall back to the Celery retry queue so no payment is ever lost.
    """
    from .models import MpesaSTKRequest
    from .settlement import run_collection_settled

    try:
        stk = MpesaSTKRequest.objects.select_related(
            'user', 'contribution', 'welfare_fund', 'shares_fund', 'advance'
        ).get(id=stk_id)
    except MpesaSTKRequest.DoesNotExist:
        logger.error("process_stk_sync: STKRequest %s not found", stk_id)
        return

    try:
        # Read the rail model, delegate the business routing to the domain seam.
        run_collection_settled(
            payment_type=stk.payment_type, user=stk.user, amount=stk.amount,
            receipt=stk.mpesa_receipt, contribution_id=stk.contribution_id,
            welfare_fund_id=stk.welfare_fund_id, shares_fund_id=stk.shares_fund_id,
            advance_id=stk.advance_id, idempotency_seed=stk.checkout_request_id,
        )
        logger.info(
            "process_stk_sync: STKRequest %s processed synchronously — type=%s receipt=%s",
            stk_id, stk.payment_type, stk.mpesa_receipt,
        )
    except Exception:
        logger.exception(
            "process_stk_sync: failed for STKRequest %s — scheduling Celery retry",
            stk_id,
        )
        enqueue_stk_processing(stk_id)
