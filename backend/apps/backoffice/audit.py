"""
Ops audit — every Back Office action is attributable.

Thin wrapper over the append-only ``AuditEvent`` (ADR-0019) that captures actor,
action, target, tenant, request metadata (IP, request id) and an arbitrary detail
payload. Never raises into the caller: an audit failure must not fail the action,
but it is logged loudly.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _client_ip(request):
    if request is None:
        return None
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or None


def record_action(
    *,
    action: str,
    actor=None,
    request=None,
    target_type: str = "",
    target_id="",
    metadata: dict | None = None,
    tenant=None,
):
    """Write one ops audit row. ``action`` is a dotted verb, e.g.
    ``ops.verification.approved`` or ``ops.export.generated``."""
    from apps.audit.models import AuditEvent

    if actor is None and request is not None:
        actor = getattr(request, "user", None)
    actor = actor if (actor is not None and getattr(actor, "pk", None)) else None
    actor_label = ""
    if actor is not None:
        actor_label = getattr(actor, "phone_number", "") or getattr(actor, "name", "") or ""

    request_id = ""
    if request is not None:
        request_id = request.headers.get("X-Request-ID", "") or request.META.get("HTTP_X_REQUEST_ID", "")

    try:
        AuditEvent.objects.create(
            actor=actor,
            actor_label=actor_label or "system",
            action=action,
            target_type=target_type or "",
            target_id=str(target_id) if target_id != "" else "",
            metadata=metadata or {},
            tenant=tenant,
            ip_address=_client_ip(request),
            request_id=request_id,
        )
    except Exception:  # never let auditing break the operation
        logger.exception("Failed to write ops AuditEvent for action=%s", action)
