"""
Safaricom IP allowlist permission for M-Pesa webhook views.

Set SAFARICOM_CALLBACK_IPS in settings to the list of Safaricom production
IP addresses.  When the list is empty (default for dev/staging), all IPs pass.

Safaricom's published IPs as of 2025: 196.201.214.0/24, 196.201.216.0/24.
The final list should come from your Safaricom account team or Daraja portal.
"""
from django.conf import settings
from rest_framework.permissions import BasePermission


class SafaricomIPPermission(BasePermission):
    """
    Allow only requests originating from Safaricom's callback IPs.

    Bypassed when settings.SAFARICOM_CALLBACK_IPS is empty so that local
    development and sandbox environments work without configuration.
    """

    def has_permission(self, request, view):
        allowed = getattr(settings, 'SAFARICOM_CALLBACK_IPS', [])
        if not allowed:
            return True

        # Prefer the first IP in X-Forwarded-For (set by load balancers).
        forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
        ip = forwarded.split(',')[0].strip() if forwarded else ''
        if not ip:
            ip = request.META.get('REMOTE_ADDR', '')

        if ip not in allowed:
            import logging
            logging.getLogger(__name__).warning(
                "SafaricomIPPermission: blocked request from %s — not in allowlist", ip
            )
            return False
        return True
