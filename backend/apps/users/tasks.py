import logging

import requests
from celery import shared_task

logger = logging.getLogger(__name__)

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    queue='notifications',
)
def send_kyc_verification_email(self, *, email, given_names, verify_url, user_id):
    """Send the KYC email-verification link out-of-band.

    Render's free tier blocks outbound SMTP (connections to smtp port time out),
    so when BREVO_API_KEY is set we deliver over Brevo's HTTP API on port 443.
    Without it we fall back to Django's email backend (console in dev/CI). Running
    in a Celery task keeps the HTTP request fast and lets delivery retry.
    """
    from django.conf import settings

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
        api_key = getattr(settings, 'BREVO_API_KEY', '')
        if api_key:
            _send_via_brevo_api(api_key, settings.DEFAULT_FROM_EMAIL, email, subject, body)
        else:
            from django.core.mail import send_mail
            send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False)
        logger.info("KYC verification email sent to %s for user %s", email, user_id)
    except Exception as exc:
        logger.exception("Failed to send KYC verification email to %s", email)
        raise self.retry(exc=exc)


def _send_via_brevo_api(api_key, from_email, to_email, subject, body):
    """Deliver one email via Brevo's transactional HTTP API (port 443)."""
    from email.utils import parseaddr

    name, addr = parseaddr(from_email)
    payload = {
        "sender": {"email": addr, "name": name or "WEPL"},
        "to": [{"email": to_email}],
        "subject": subject,
        "textContent": body,
    }
    resp = requests.post(
        BREVO_API_URL,
        json=payload,
        headers={
            "api-key": api_key,
            "accept": "application/json",
            "content-type": "application/json",
        },
        timeout=15,
    )
    resp.raise_for_status()


@shared_task(queue='default')
def expire_restrictions():
    """Sweep account restrictions past their expiry into the EXPIRED state.

    Reads already treat a past-expiry restriction as inactive, so enforcement is
    correct without this; the sweep keeps the stored state honest (and fires the
    lifecycle transition) for the ops directory. Runs hourly via Celery Beat."""
    from apps.users.services import RestrictionService
    n = RestrictionService.expire_due()
    if n:
        logger.info("expire_restrictions: %d restriction(s) expired.", n)
    return {"expired": n}
