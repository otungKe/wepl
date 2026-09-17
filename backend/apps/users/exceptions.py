"""User/KYC domain exceptions and their HTTP rendering (ADR-0022, ADR-0031).

``KYCRequired`` and its structured 403 envelope belong to the users context, not to
Core's platform layer. The renderer is registered with Core's exception registry at
import time; ``apps.users.apps.UsersConfig.ready()`` imports this module so the
registration happens at startup (the same pattern as policy resolvers, ADR-0009).
"""
from django.core.exceptions import PermissionDenied

from rest_framework import status
from rest_framework.response import Response

from apps.core.exceptions import register_exception_renderer


class KYCRequired(PermissionDenied):
    """
    Raised when a Tier-0 (identity-verified but not KYC-approved) user attempts a
    Tier-1 (full-access) action. A subclass of Django's PermissionDenied so it can
    be raised from services, Celery tasks and WS consumers (like the policy layer),
    but the handler renders a *structured* 403 the client can branch on:

        {"code": "KYC_REQUIRED", "message": "...", "next_step": "/kyc/start"}

    See apps/users/tiers.py (AccessPolicy) and ADR-0022.
    """
    code = 'KYC_REQUIRED'
    default_message = 'Complete identity verification to unlock all platform features.'
    next_step = '/kyc/start'

    def __init__(self, message=None, next_step=None):
        self.message = message or self.default_message
        if next_step:
            self.next_step = next_step
        super().__init__(self.message)


def _render_kyc_required(exc: KYCRequired) -> Response:
    """Structured 403 envelope. Registered before_drf because DRF's default handler
    would otherwise convert this PermissionDenied subclass into a generic 403 and
    swallow the envelope."""
    return Response(
        {'code': exc.code, 'message': exc.message, 'next_step': exc.next_step},
        status=status.HTTP_403_FORBIDDEN,
    )


register_exception_renderer(KYCRequired, _render_kyc_required, before_drf=True)
