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


def custom_exception_handler(exc, context):
    """
    Augments DRF's default handler to also handle Django-native exceptions
    that DRF does not convert by default.
    """
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

    # Everything else: let Django's 500 handler deal with it.
    # This ensures real bugs surface in Sentry rather than being swallowed as 400s.
    return None
