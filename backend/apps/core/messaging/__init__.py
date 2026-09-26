"""Messaging transports: the platform's way to send a text or an email.

Callers say what to send and to whom; which gateway carries it (Africa's
Talking or the console for SMS, Brevo's HTTP API or Django's email backend for
email) is settings, decided here. Like the payment and identity ports, nothing
above this package names a vendor. It imports no domain app.
"""
from .email import send_email
from .sms import SMSGateway, get_sms_gateway

__all__ = ["SMSGateway", "get_sms_gateway", "send_email"]
