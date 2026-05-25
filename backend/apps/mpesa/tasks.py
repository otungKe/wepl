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
        if stk.payment_type == "welfare" and stk.welfare_fund_id:
            from apps.contributions.services import WelfareService
            WelfareService.contribute_to_welfare(
                stk.welfare_fund_id,
                stk.user,
                stk.amount,
                mpesa_receipt=stk.mpesa_receipt,
            )

        elif stk.payment_type == "shares" and stk.shares_fund_id:
            from apps.mpesa.views import _process_shares_purchase
            _process_shares_purchase(stk)

        elif stk.payment_type == "advance_repayment" and stk.advance_id:
            from apps.contributions.services import EmergencyAdvanceService
            EmergencyAdvanceService.repay(
                stk.advance_id,
                stk.user,
                stk.amount,
                mpesa_receipt=stk.mpesa_receipt,
            )

        else:
            from apps.contributions.services import ContributionService
            idempotency_key = f"contrib-stk-{stk.mpesa_receipt or stk.checkout_request_id}"
            ContributionService.contribute(
                stk.user,
                stk.contribution_id,
                stk.amount,
                mpesa_receipt=stk.mpesa_receipt,
                idempotency_key=idempotency_key,
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
