import threading
import uuid

_local = threading.local()


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
        request_id = request.META.get('HTTP_X_REQUEST_ID') or str(uuid.uuid4())
        request.request_id = request_id
        _local.request_id = request_id

        response = self.get_response(request)
        response['X-Request-Id'] = request_id

        _local.request_id = None
        return response
