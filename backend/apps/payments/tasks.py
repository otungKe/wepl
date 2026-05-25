import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=10,
    default_retry_delay=15,
    queue='payments',
)
def poll_mpesa_stk_status(self, checkout_request_id: str):
    """
    Poll Safaricom for the result of an STK Push request.
    Called after the initial push; retries every 15 seconds up to 10 times
    (2.5 minutes total) before giving up and marking the request FAILED.
    """
    from apps.mpesa.models import MpesaSTKRequest

    try:
        stk = MpesaSTKRequest.objects.get(checkout_request_id=checkout_request_id)
    except MpesaSTKRequest.DoesNotExist:
        logger.error("poll_mpesa_stk_status: STK request %s not found", checkout_request_id)
        return

    if stk.status != 'PENDING':
        # Already resolved by callback — nothing to do
        return

    try:
        from apps.mpesa.services import MpesaService
        MpesaService.query_stk_status(checkout_request_id)
    except Exception as exc:
        logger.warning(
            "poll_mpesa_stk_status: query failed for %s (%s), retrying",
            checkout_request_id, exc,
        )
        raise self.retry(exc=exc)

    # Re-fetch after query
    stk.refresh_from_db()
    if stk.status == 'PENDING' and self.request.retries >= self.max_retries - 1:
        stk.status = 'FAILED'
        stk.result_desc = 'Timed out waiting for M-Pesa confirmation.'
        stk.save()
        logger.error("poll_mpesa_stk_status: timed out for %s", checkout_request_id)
