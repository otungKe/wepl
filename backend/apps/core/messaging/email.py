"""Sending one plain-text email.

Render's free tier blocks outbound SMTP (connections to the SMTP port time
out), so when ``BREVO_API_KEY`` is set the email goes over Brevo's HTTP API on
port 443. Without it, Django's ``EMAIL_BACKEND`` sends it (console in dev/CI).
Moved from ``apps/users/tasks.py`` in the boundary audit (step 7).
"""
from email.utils import parseaddr

import requests
from django.conf import settings

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


def send_email(to: str, subject: str, body: str) -> None:
    """Send ``body`` to ``to``. Raises on failure so a Celery caller can retry."""
    api_key = getattr(settings, 'BREVO_API_KEY', '')
    if api_key:
        _send_via_brevo_api(api_key, settings.DEFAULT_FROM_EMAIL, to, subject, body)
        return
    from django.core.mail import send_mail
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [to], fail_silently=False)


def _send_via_brevo_api(api_key, from_email, to_email, subject, body):
    """Deliver one email via Brevo's transactional HTTP API (port 443)."""
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
