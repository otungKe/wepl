"""
SMS gateway abstraction.

The previous code called ``settings.AT_SMS.send(...)`` but ``AT_SMS`` was
initialised by importing and initialising africastalking at settings load time.
This caused two problems:
  1. If the africastalking package was absent the entire Django settings module
     failed to import, breaking every management command and test run.
  2. Initialisation with empty credentials (common in CI) raised obscure errors
     far from the call site.

This module makes the gateway explicit, configurable via settings.SMS_BACKEND,
and lazy — AfricasTalkingGateway only validates credentials at first send, not
at import time.

Usage:
    from .sms import get_sms_gateway
    get_sms_gateway().send("Your code is 1234", "254712345678")
"""
import logging
from functools import lru_cache

from django.conf import settings

logger = logging.getLogger(__name__)


class SMSGateway:
    """Interface — subclasses must implement send(message, phone)."""

    def send(self, message: str, phone: str) -> None:  # pragma: no cover
        raise NotImplementedError


class ConsoleSMSGateway(SMSGateway):
    """Dev / CI gateway — logs the message, never hits the network."""

    def send(self, message: str, phone: str) -> None:
        logger.info("[SMS:console] to=%s msg=%r", phone, message)


class AfricasTalkingGateway(SMSGateway):
    """
    Africa's Talking production gateway.

    Credentials are validated on first instantiation so that a misconfigured
    production environment raises a clear RuntimeError at startup, not a
    cryptic AttributeError buried in an OTP handler.
    """

    def __init__(self):
        api_key  = getattr(settings, "AT_API_KEY",  "") or ""
        username = getattr(settings, "AT_USERNAME", "") or ""
        if not api_key or not username:
            raise RuntimeError(
                "SMS_BACKEND='at' but AT_API_KEY / AT_USERNAME are not set. "
                "Add them to your environment or set SMS_BACKEND=console for dev."
            )
        try:
            import africastalking
        except ImportError as exc:
            raise RuntimeError(
                "africastalking package is not installed. "
                "Run: pip install africastalking"
            ) from exc

        africastalking.initialize(username, api_key)
        self._sms       = africastalking.SMS
        self._sender_id = getattr(settings, "AT_SENDER_ID", None) or None
        logger.info("AfricasTalkingGateway initialised (username=%s)", username)

    def send(self, message: str, phone: str) -> None:
        self._sms.send(message, [phone], sender_id=self._sender_id)
        logger.info("[SMS:AT] sent to %s", phone)


@lru_cache(maxsize=1)
def get_sms_gateway() -> SMSGateway:
    """
    Return the configured SMS gateway, cached for the process lifetime.

    Backend selection (settings.SMS_BACKEND):
        'at'      → AfricasTalkingGateway (production)
        'console' → ConsoleSMSGateway (dev / CI)
        ''        → auto: 'console' under DEBUG, 'at' in production
    """
    backend = (getattr(settings, "SMS_BACKEND", "") or "").strip()
    if not backend:
        backend = "console" if settings.DEBUG else "at"

    if backend == "at":
        return AfricasTalkingGateway()

    logger.debug("SMS gateway: console (backend=%r)", backend)
    return ConsoleSMSGateway()
