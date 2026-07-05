import threading
import uuid
from datetime import timedelta

from django.utils import timezone

_local = threading.local()

# How often to write last_seen to the DB — avoids a write on every request.
# A user is considered "online" if last seen within ONLINE_THRESHOLD.
LAST_SEEN_UPDATE_INTERVAL = timedelta(seconds=60)
ONLINE_THRESHOLD          = timedelta(minutes=5)


def get_current_request_id() -> str | None:
    return getattr(_local, 'request_id', None)


class RequestIdMiddleware:
    """
    Attaches a UUID request ID to every request for log correlation.

    Sources, in priority order:
      1. X-Request-Id header from the client (e.g. a load balancer or API gateway)
      2. A freshly generated UUID4

    The resolved ID is available as:
      - request.request_id       — in views / DRF handlers
      - get_current_request_id() — in services / tasks (thread-local)
      - X-Request-Id response header — returned to the caller for client-side tracing
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from apps.core import observability

        request_id = request.META.get('HTTP_X_REQUEST_ID') or str(uuid.uuid4())
        request.request_id = request_id
        _local.request_id = request_id
        observability.bind(request_id=request_id)

        try:
            response = self.get_response(request)
        finally:
            # Clear the whole log context (request_id + actor/tenant bound during
            # dispatch) so nothing leaks onto the next request on this thread.
            observability.clear()
        response['X-Request-Id'] = request_id

        # Update last_seen for authenticated users.
        # Only write to DB if the stored value is stale by more than
        # LAST_SEEN_UPDATE_INTERVAL — avoids a DB write on every request.
        user = getattr(request, 'user', None)
        # last_seen is a customer-User concept; Back Office StaffAccounts (and
        # AnonymousUser) don't have it, so guard before touching it.
        if user and user.is_authenticated and hasattr(user, 'last_seen'):
            now = timezone.now()
            if (
                user.last_seen is None
                or (now - user.last_seen) >= LAST_SEEN_UPDATE_INTERVAL
            ):
                try:
                    from django.contrib.auth import get_user_model
                    get_user_model().objects.filter(pk=user.pk).update(last_seen=now)
                    user.last_seen = now   # keep in-memory copy consistent
                except Exception:
                    pass

        _local.request_id = None
        return response
