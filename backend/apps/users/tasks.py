import logging

from celery import shared_task

from apps.core.messaging import send_email

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    queue='notifications',
)
def send_kyc_verification_email(self, *, email, given_names, verify_url, user_id):
    """Send the KYC email-verification link out-of-band.

    ``apps.core.messaging.send_email`` picks the transport (Brevo's HTTP API when
    BREVO_API_KEY is set, Django's email backend otherwise). Running in a Celery
    task keeps the HTTP request fast and lets delivery retry.
    """
    subject = "Verify your email — WEPL KYC"
    body = (
        f"Hi {given_names},\n\n"
        f"Thank you for submitting your identity verification on WEPL.\n\n"
        f"Please click the link below to verify your email address and complete "
        f"the verification process:\n\n"
        f"  {verify_url}\n\n"
        f"This link is valid for 48 hours.\n\n"
        f"If you did not submit a KYC application on WEPL, please ignore this email.\n\n"
        f"— The WEPL Team"
    )

    try:
        send_email(email, subject, body)
        logger.info("KYC verification email sent to %s for user %s", email, user_id)
    except Exception as exc:
        logger.exception("Failed to send KYC verification email to %s", email)
        raise self.retry(exc=exc)


@shared_task(queue='default')
def expire_restrictions():
    """Sweep account restrictions past their expiry into the EXPIRED state.

    Reads already treat a past-expiry restriction as inactive, so enforcement is
    correct without this; the sweep keeps the stored state honest (and fires the
    lifecycle transition) for the ops directory. Runs hourly via Celery Beat."""
    from apps.controls.restrictions import RestrictionService
    n = RestrictionService.expire_due()
    if n:
        logger.info("expire_restrictions: %d restriction(s) expired.", n)
    return {"expired": n}
