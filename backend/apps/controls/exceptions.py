"""Controls-chokepoint domain exceptions and their HTTP rendering (ADR-0007, ADR-0031).

``LimitExceeded`` (DENY) and ``ControlHeld`` (HOLD) belong to the controls context,
not to Core's platform layer. Their renderers durably record the blocked movement to
the review queue (best-effort, outside the rolled-back money transaction) and map to
422 / 409. Registered with Core's exception registry at import time;
``apps.controls.apps.ControlsConfig.ready()`` imports this module so registration
happens at startup.
"""
import logging

from rest_framework import status
from rest_framework.response import Response

from apps.core.exceptions import register_exception_renderer

logger = logging.getLogger(__name__)


class LimitExceeded(Exception):
    """
    Raised by the controls layer at the posting chokepoint when a money movement
    breaches a configured limit and the rule action is DENY.

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


def _record_blocked(exc) -> None:
    """Durably persist the blocked movement to the review queue. Runs AFTER the
    service's @transaction.atomic has rolled back, so the record persists even
    though the money movement did not. Best-effort — a recording failure must never
    mask the original control response."""
    try:
        from .review import record_blocked_movement
        record_blocked_movement(exc)
    except Exception:  # pragma: no cover - audit must not break the response
        logger.exception("Failed to record held/denied movement")


def _render_limit_exceeded(exc: LimitExceeded) -> Response:
    _record_blocked(exc)
    return Response({'error': str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)


def _render_control_held(exc: ControlHeld) -> Response:
    _record_blocked(exc)
    return Response({'error': str(exc)}, status=status.HTTP_409_CONFLICT)


register_exception_renderer(LimitExceeded, _render_limit_exceeded)
register_exception_renderer(ControlHeld, _render_control_held)
