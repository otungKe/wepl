"""
M-Pesa Celery tasks.

process_stk_payment is the single, retryable path for processing a successful
STK callback.  STKCallbackView enqueues it via on_commit so processing happens
outside the HTTP request/response cycle and is retried on transient failures.
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

    Called via on_commit after STKCallbackView atomically claims the callback row.
    Retries up to 3 times on any transient failure (DB, network, constraint).

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
        from apps.contributions.settlement import on_collection_settled
        on_collection_settled(
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
