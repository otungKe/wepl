"""Rate throttles that fail **open** when their cache backend (Redis) is down.

Rate limiting is best-effort capacity/abuse protection — it must never be the
single point of failure that 500s the whole API. DRF's ``SimpleRateThrottle``
reads and writes request history through the default cache on *every* request,
inside ``APIView.initial()`` (before the view runs). So when Redis is unreachable
— e.g. ``ConnectionError: max number of clients reached`` — *every* throttled
endpoint (which is all of them, via ``DEFAULT_THROTTLE_CLASSES``) raises and
returns HTTP 500. A Redis capacity blip becomes a total API outage.

These subclasses catch cache errors in ``allow_request`` and let the request
through, trading rate limiting away for the duration of the outage rather than
availability. The failure is logged so the degradation is visible in the logs
and can drive an alert.

Security note: the auth/abuse throttles (PIN login, OTP, STK) also inherit this
fail-open behaviour, so during a Redis outage their brute-force protection is
degraded. That is a deliberate trade — the alternative (fail closed) blocks all
logins/OTPs during the same outage — and Redis outages should be rare, brief and
alarmed. Revisit if a fail-closed posture for auth is preferred.
"""
import logging

from rest_framework.throttling import (
    AnonRateThrottle, ScopedRateThrottle, UserRateThrottle,
)

logger = logging.getLogger(__name__)


class FailOpenThrottleMixin:
    """Allow the request if the throttle's cache backend errors out."""

    def allow_request(self, request, view):
        try:
            return super().allow_request(request, view)
        except Exception:
            # Cache/Redis unreachable — degrade to no rate limiting rather than
            # 500 the endpoint. Logged (with traceback) so the outage is visible.
            logger.warning(
                "Throttle backend unavailable (%s) for %s — allowing request; "
                "rate limiting is degraded until the cache recovers.",
                type(self).__name__, getattr(request, "path", "?"),
                exc_info=True,
            )
            return True


class ResilientAnonRateThrottle(FailOpenThrottleMixin, AnonRateThrottle):
    pass


class ResilientUserRateThrottle(FailOpenThrottleMixin, UserRateThrottle):
    pass


class ResilientScopedRateThrottle(FailOpenThrottleMixin, ScopedRateThrottle):
    pass
