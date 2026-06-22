"""Reset the RLS tenant context at the end of every request (Phase 6, P6-04).

DB connections are pooled (CONN_MAX_AGE), so a tenant pinned during one request
must be cleared before the connection serves another — otherwise tenant context
would leak across requests. TenantJWTAuthentication sets the context; this
middleware always clears it.
"""
import logging

from .rls import clear_current_tenant

logger = logging.getLogger(__name__)


class TenantRLSMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            return self.get_response(request)
        finally:
            try:
                clear_current_tenant()
            except Exception:  # pragma: no cover - reset must never break the response
                logger.exception("Failed to reset tenant RLS context")
