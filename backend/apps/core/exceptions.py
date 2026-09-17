"""
Central DRF exception handler + shared *platform* exceptions + a renderer registry.

Platform exceptions (owned by Core)
-----------------------------------
TransitionError    — state-machine transition_to() illegal edge / lost concurrent
    UPDATE race.  Maps to 409.  Raised by ledger, payments and verification state
    machines alike — a cross-cutting mechanism with no single business owner.

RateLimitError     — service-layer rate-limit breach (OTP, SMS, …).  Maps to 429.

ServiceUnavailable — a hard infrastructure dependency is transiently down (e.g. the
    OTP store).  Maps to 503 with a Retry-After hint.

These stay in Core because they are cross-cutting mechanisms, not domain concepts.
*Business* exceptions (KYC gating, control holds/denials) live in their owning app
and register their own renderer via ``register_exception_renderer`` from that app's
``AppConfig.ready()`` — so Core imports no business app and names no domain concept
(ADR-0031, the same registry discipline as ``apps.core.policy``).

Renderer registry
-----------------
An app maps its exception to an HTTP response by registering a renderer::

    from apps.core.exceptions import register_exception_renderer
    register_exception_renderer(MyError, lambda exc: Response(..., status=...))

``before_drf=True`` runs the renderer *before* DRF's default handler — needed for a
structured ``PermissionDenied`` subclass whose envelope DRF would otherwise flatten.

Exception handler
-----------------
custom_exception_handler resolves, in order:
  1. registered before-DRF renderers,
  2. DRF's own exceptions,
  3. Django-native built-ins (PermissionDenied / ValidationError / Http404),
  4. registered after-DRF renderers (Core primitives + business apps),
  5. otherwise → Django's 500 handler (so real bugs surface in Sentry).

Register in settings:
    REST_FRAMEWORK = {
        'EXCEPTION_HANDLER': 'apps.core.exceptions.custom_exception_handler',
    }

Response shapes:
    400  {"error": "<message>"} / {"errors": [...]}   — ValidationError
    403  {"error": "<message>"}                        — PermissionDenied
    404  {"error": "Not found."}                       — Http404
    409  {"error": "<message>"}                        — TransitionError
    429  {"error": "<message>"}                        — RateLimitError
    503  {"error": "<message>"}                        — ServiceUnavailable
    (business apps register their own shapes, e.g. KYC 403, control 422/409)
"""
from typing import Callable

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_default_handler


class TransitionError(Exception):
    """
    Raised by a state machine's transition_to() when:
      - the requested transition is not allowed for the current state
        (programming error or client abuse), or
      - the UPDATE WHERE state=<current> returned 0 rows because a concurrent
        worker already advanced the state (race condition).

    Kept separate from ValidationError so callers can distinguish a domain
    validation failure (400) from a concurrency conflict (409).
    """


class RateLimitError(Exception):
    """
    Raised by service-layer rate-limit checks (OTP, SMS, etc.).

    Maps to HTTP 429 Too Many Requests via the custom exception handler,
    so services remain free of HTTP concerns and views need no try/except.
    """


class ServiceUnavailable(Exception):
    """
    Raised when a hard infrastructure dependency is transiently unavailable and
    the request cannot proceed — e.g. the OTP store (cache/Redis) is down, so an
    OTP can neither be issued nor verified.

    Maps to HTTP 503 Service Unavailable (with a Retry-After hint) so the client
    shows a clean "try again shortly" rather than a raw 500. Reserved for genuine
    dependency outages, not validation or rate limiting.
    """


# ── Renderer registry (ADR-0031) ─────────────────────────────────────────────
# (exc_type, renderer(exc) -> Response, before_drf). Business apps append their own
# from AppConfig.ready(); Core registers only its own platform primitives (below).
Renderer = Callable[[Exception], Response]
_EXCEPTION_RENDERERS: list[tuple[type, Renderer, bool]] = []


def register_exception_renderer(exc_type: type, renderer: Renderer, *,
                                before_drf: bool = False) -> None:
    """Register a Response renderer for ``exc_type``.

    Called from an app's ``AppConfig.ready()`` so Core needs no knowledge of the
    app's exceptions. ``before_drf`` runs the renderer ahead of DRF's default
    handler (for a structured exception DRF would otherwise flatten). More
    specific types should register before broader ones, since the first
    ``isinstance`` match in registration order wins.
    """
    _EXCEPTION_RENDERERS.append((exc_type, renderer, before_drf))


def _render_registered(exc, *, before_drf: bool):
    for exc_type, renderer, flag in _EXCEPTION_RENDERERS:
        if flag == before_drf and isinstance(exc, exc_type):
            return renderer(exc)
    return None


def custom_exception_handler(exc, context):
    """
    Augments DRF's default handler with a renderer registry and the Django-native
    exceptions DRF does not convert by default.
    """
    # 1. Registered before-DRF renderers (e.g. a structured PermissionDenied
    #    subclass whose envelope DRF's default handler would otherwise flatten).
    rendered = _render_registered(exc, before_drf=True)
    if rendered is not None:
        return rendered

    # 2. Let DRF handle its own exceptions first (e.g. rest_framework.exceptions.*,
    #    and Django's PermissionDenied / Http404 which DRF also converts).
    response = drf_default_handler(exc, context)
    if response is not None:
        return response

    # 3. Django-native built-ins DRF may not have converted.
    if isinstance(exc, PermissionDenied):
        return Response(
            {'error': str(exc) or 'You do not have permission to perform this action.'},
            status=status.HTTP_403_FORBIDDEN,
        )

    if isinstance(exc, ValidationError):
        # ValidationError can carry a single message or a list.
        if hasattr(exc, 'message_dict'):
            return Response(exc.message_dict, status=status.HTTP_400_BAD_REQUEST)
        elif hasattr(exc, 'messages') and len(exc.messages) > 1:
            return Response({'errors': exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        else:
            msg = exc.message if hasattr(exc, 'message') else str(exc)
            return Response({'error': msg}, status=status.HTTP_400_BAD_REQUEST)

    if isinstance(exc, Http404):
        return Response({'error': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    # 4. Registered after-DRF renderers (Core primitives + business apps).
    rendered = _render_registered(exc, before_drf=False)
    if rendered is not None:
        return rendered

    # 5. Everything else: let Django's 500 handler deal with it, so real bugs
    #    surface in Sentry rather than being swallowed as 400s.
    return None


# ── Core registers its own platform primitives ───────────────────────────────
def _render_transition_error(exc):
    # In practice caught internally (tasks/webhooks); if one escapes to a view the
    # client should know it's a concurrency conflict.
    return Response({'error': str(exc)}, status=status.HTTP_409_CONFLICT)


def _render_rate_limit_error(exc):
    return Response({'error': str(exc)}, status=status.HTTP_429_TOO_MANY_REQUESTS)


def _render_service_unavailable(exc):
    resp = Response(
        {'error': str(exc) or 'Service temporarily unavailable. Please try again shortly.'},
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )
    resp['Retry-After'] = '30'
    return resp


register_exception_renderer(TransitionError, _render_transition_error)
register_exception_renderer(RateLimitError, _render_rate_limit_error)
register_exception_renderer(ServiceUnavailable, _render_service_unavailable)
