import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    queue='notifications',
)
def send_kyc_verification_email(self, *, email, given_names, verify_url, user_id):
    """Send the KYC email-verification link out-of-band.

    The SMTP round-trip used to run inline in the ASGI request handler, where a
    slow/blocked connection hung the request until Daphne killed the worker.
    Doing it here keeps the HTTP request fast and lets delivery retry on
    transient SMTP failures. EMAIL_TIMEOUT (settings) bounds the connection so a
    stalled send fails fast instead of tying up the worker.
    """
    from django.conf import settings
    from django.core.mail import send_mail

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
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False)
        logger.info("KYC verification email sent to %s for user %s", email, user_id)
    except Exception as exc:
        logger.exception("Failed to send KYC verification email to %s", email)
        raise self.retry(exc=exc)
