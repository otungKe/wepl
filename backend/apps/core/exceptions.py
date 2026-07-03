"""
Central DRF exception handler + shared domain exceptions.

Custom exceptions
-----------------
TransitionError  — raised by state machine transition_to() when a transition is
    illegal (wrong graph) or lost a concurrent UPDATE race.  Maps to 409.

RateLimitError   — raised by services when a client has exceeded a rate limit
    (OTP requests, SMS, etc.).  Maps to 429.  Keeps services free of HTTP
    concerns while giving the view layer the right status code for free.

Exception handler
-----------------
Converts Django's PermissionDenied and ValidationError into clean DRF
JSON responses so views never need bare try/except blocks for these cases.

Register in settings:
    REST_FRAMEWORK = {
        'EXCEPTION_HANDLER': 'apps.core.exceptions.custom_exception_handler',
    }

Response shapes:
    403  {"error": "<message>"}         — PermissionDenied
    400  {"error": "<message>"}         — ValidationError (single message)
    400  {"errors": ["msg1", "msg2"]}   — ValidationError (multiple messages)
    404  {"error": "Not found."}        — Http404
    409  {"error": "<message>"}         — TransitionError (state machine conflict)
    429  {"error": "<message>"}         — RateLimitError
    All other exceptions fall through to Django's 500 handler (and Sentry).
"""
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_default_handler


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


class TransitionError(Exception):
    """
    Raised by FinancialTransaction.transition_to() when:
      - The requested transition is not allowed by VALID_TRANSITIONS for the
        current state (programming error or client abuse), or
      - The UPDATE WHERE state=<current> returned 0 rows because a concurrent
        worker already advanced the state (race condition).

    Kept separate from ValidationError so callers can distinguish between
    a domain validation failure (400) and a concurrency conflict (409).
    """


class RateLimitError(Exception):
    """
    Raised by service-layer rate-limit checks (OTP, SMS, etc.).

    Maps to HTTP 429 Too Many Requests via the custom exception handler,
    so services remain free of HTTP concerns and views need no try/except.
    """


class LimitExceeded(Exception):
    """
    Raised by the controls layer (apps.controls) at the posting chokepoint when a
    money movement breaches a configured limit and the rule action is DENY.

    Maps to HTTP 422 Unprocessable Entity — the request was well-formed but a
    business control rejected it before any journal was written. Carries a
    ``context`` dict describing the blocked movement (recorded for review).
    """
    def __init__(self, message, context=None):
        super().__init__(message)
        self.context = context or {}


class ControlHeld(Exception):
    """
    Raised by the controls layer when a money movement trips a rule whose action
    is HOLD (e.g. velocity/anomaly). The movement is not posted; it is flagged for
    manual review. Maps to HTTP 409 Conflict so the client knows the request is
    parked rather than permanently rejected. Carries a ``context`` dict.
    """
    def __init__(self, message, context=None):
        super().__init__(message)
        self.context = context or {}


def custom_exception_handler(exc, context):
    """
    Augments DRF's default handler to also handle Django-native exceptions
    that DRF does not convert by default.
    """
    # KYCRequired → 403 with the structured tier envelope. Handled BEFORE DRF's
    # default handler, which would otherwise convert this Django PermissionDenied
    # subclass into a generic {"detail": ...} 403 and swallow the envelope.
    if isinstance(exc, KYCRequired):
        return Response(
            {'code': exc.code, 'message': exc.message, 'next_step': exc.next_step},
            status=status.HTTP_403_FORBIDDEN,
        )

    # Let DRF handle its own exceptions first (e.g. rest_framework.exceptions.*)
    response = drf_default_handler(exc, context)
    if response is not None:
        return response

    # Django PermissionDenied → 403
    if isinstance(exc, PermissionDenied):
        return Response(
            {'error': str(exc) or 'You do not have permission to perform this action.'},
            status=status.HTTP_403_FORBIDDEN,
        )

    # Django ValidationError → 400
    if isinstance(exc, ValidationError):
        # ValidationError can carry a single message or a list
        if hasattr(exc, 'message_dict'):
            # Field-keyed errors from model clean() — rare in service layer
            return Response(exc.message_dict, status=status.HTTP_400_BAD_REQUEST)
        elif hasattr(exc, 'messages') and len(exc.messages) > 1:
            return Response(
                {'errors': exc.messages},
                status=status.HTTP_400_BAD_REQUEST,
            )
        else:
            msg = exc.message if hasattr(exc, 'message') else str(exc)
            return Response({'error': msg}, status=status.HTTP_400_BAD_REQUEST)

    # Http404 → 404
    if isinstance(exc, Http404):
        return Response({'error': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    # TransitionError → 409 Conflict
    # In practice these are caught internally (tasks/webhooks), but if one
    # escapes to a view the client should know it's a concurrency conflict.
    if isinstance(exc, TransitionError):
        return Response({'error': str(exc)}, status=status.HTTP_409_CONFLICT)

    # RateLimitError → 429 Too Many Requests
    if isinstance(exc, RateLimitError):
        return Response({'error': str(exc)}, status=status.HTTP_429_TOO_MANY_REQUESTS)

    # Controls (Phase 3): durably record the blocked movement to the review queue.
    # This runs AFTER the service's @transaction.atomic has rolled back, so the
    # record persists even though the FinancialTransaction did not. Best-effort —
    # a recording failure must never mask the original control response.
    if isinstance(exc, (LimitExceeded, ControlHeld)):
        try:
            from apps.controls.review import record_blocked_movement
            record_blocked_movement(exc)
        except Exception:  # pragma: no cover - audit must not break the response
            import logging
            logging.getLogger(__name__).exception("Failed to record held/denied movement")

    # LimitExceeded → 422 (control rejected the movement before posting)
    if isinstance(exc, LimitExceeded):
        return Response({'error': str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

    # ControlHeld → 409 (movement parked for manual review)
    if isinstance(exc, ControlHeld):
        return Response({'error': str(exc)}, status=status.HTTP_409_CONFLICT)

    # Everything else: let Django's 500 handler deal with it.
    # This ensures real bugs surface in Sentry rather than being swallowed as 400s.
    return None
