"""Structured logging context + JSON formatter (ADR-0020).

Every log line should carry the request id, tenant id and actor id so a single
incident can be traced across services. Those values live in a thread-local
"log context" bound during request/auth handling and read by a logging filter,
so call sites just use ``logging`` as usual.

Binding points:
  * ``request_id`` — ``core.middleware.RequestIdMiddleware`` (per request)
  * ``actor_id``   — the JWT auth class, once the user is resolved
  * ``tenant_id``  — the tenant-aware JWT auth class, when it pins the tenant

The context is cleared at the end of each request (middleware) and at Celery task
boundaries, so nothing leaks across requests/tasks on a reused thread.
"""
import json
import logging
import threading
from datetime import datetime, timezone

_ctx = threading.local()


def bind(**kwargs) -> None:
    for key, value in kwargs.items():
        setattr(_ctx, key, value)


def get(name, default=None):
    return getattr(_ctx, name, default)


def clear() -> None:
    _ctx.__dict__.clear()


class ContextFilter(logging.Filter):
    """Attach the bound request/tenant/actor context to every record."""

    def filter(self, record):
        record.request_id = get("request_id", "") or ""
        record.tenant_id = get("tenant_id")
        record.actor_id = get("actor_id")
        return True


class JSONFormatter(logging.Formatter):
    """One JSON object per line, with the log context and (if any) exception."""

    def format(self, record):
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "request_id": getattr(record, "request_id", "") or "",
            "tenant_id": getattr(record, "tenant_id", None),
            "actor_id": getattr(record, "actor_id", None),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)
