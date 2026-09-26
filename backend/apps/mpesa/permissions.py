"""
Safaricom IP allowlist permission for M-Pesa webhook views.

Set SAFARICOM_CALLBACK_IPS (env, comma-separated addresses or CIDR ranges) to
Safaricom's callback addresses. When the list is empty (dev/sandbox), every
sender passes; ``config/settings/production.py`` refuses to boot against live
Daraja with it empty (``apps.core.deploy_checks.check_callback_allowlist``).

Safaricom's published ranges as of 2025: 196.201.214.0/24, 196.201.216.0/24.
The final list should come from your Safaricom account team or Daraja portal.
"""
import ipaddress
import logging

from django.conf import settings
from rest_framework.permissions import BasePermission

logger = logging.getLogger(__name__)


def allowlist_enforced() -> bool:
    """True when callbacks are actually restricted to Safaricom's addresses."""
    return bool(getattr(settings, 'SAFARICOM_CALLBACK_IPS', []))


def _networks(entries):
    return [ipaddress.ip_network(e.strip(), strict=False) for e in entries if e.strip()]


def sender_ip(request) -> str:
    """The address that connected to the outermost trusted proxy.

    Each of the ``SAFARICOM_CALLBACK_PROXY_HOPS`` proxies appends the address it
    saw, so the sender is that many entries from the right. Entries further left
    are supplied by the caller and prove nothing.
    """
    hops = getattr(settings, 'SAFARICOM_CALLBACK_PROXY_HOPS', 1)
    if hops <= 0:
        return request.META.get('REMOTE_ADDR', '')
    forwarded = [
        p.strip() for p in request.META.get('HTTP_X_FORWARDED_FOR', '').split(',') if p.strip()
    ]
    if len(forwarded) < hops:
        return ''
    return forwarded[-hops]


class SafaricomIPPermission(BasePermission):
    """
    Allow only requests originating from Safaricom's callback IPs.

    Bypassed when settings.SAFARICOM_CALLBACK_IPS is empty so that local
    development and sandbox environments work without configuration.
    """

    def has_permission(self, request, view):
        if not allowlist_enforced():
            return True

        ip = sender_ip(request)
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            logger.warning("SafaricomIPPermission: blocked request with no usable sender address %r", ip)
            return False

        if not any(addr in net for net in _networks(settings.SAFARICOM_CALLBACK_IPS)):
            logger.warning("SafaricomIPPermission: blocked request from %s — not in allowlist", ip)
            return False
        return True
