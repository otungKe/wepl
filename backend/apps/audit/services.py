"""Audit logging service (ADR-0019) — one tiny call to record an admin action.

    from apps.audit.services import AuditService
    AuditService.log("community.ownership_transferred", actor=request.user,
                     target=community, metadata={"to_user_id": new_owner.id})

Call it *inside* the action's transaction so the audit row commits atomically with
the change it describes.
"""
import logging

logger = logging.getLogger(__name__)


def _client_ip(request):
    if request is None:
        return None
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or None


def _actor_label(actor) -> str:
    if actor is None or not getattr(actor, "is_authenticated", False):
        return ""
    return ((getattr(actor, "name", "") or "").strip()
            or getattr(actor, "phone_number", "") or "")[:120]


class AuditService:

    @staticmethod
    def log(action, *, actor=None, target=None, target_type="", target_id="",
            metadata=None, tenant=None, request=None):
        """Write one append-only AuditEvent. Best-effort: never raises into the
        caller (auditing must not break the audited action)."""
        from .models import AuditEvent
        try:
            if target is not None and not target_type:
                target_type = target.__class__.__name__.lower()
                target_id = str(getattr(target, "pk", "") or "")

            # Tenant: explicit wins; else the tenant pinned for this request/task.
            tenant_id = None
            if tenant is not None:
                tenant_id = getattr(tenant, "id", tenant)
            else:
                from apps.tenants.rls import current_tenant_id
                tenant_id = current_tenant_id()

            from apps.core.middleware import get_current_request_id

            actor_obj = actor if (actor is not None
                                  and getattr(actor, "is_authenticated", False)) else None
            return AuditEvent.objects.create(
                actor=actor_obj,
                actor_label=_actor_label(actor),
                action=action,
                target_type=str(target_type)[:60],
                target_id=str(target_id)[:64],
                tenant_id=tenant_id,
                metadata=metadata or {},
                ip_address=_client_ip(request),
                request_id=(get_current_request_id() or "")[:64],
            )
        except Exception:  # pragma: no cover - auditing must never break the action
            logger.exception("AuditService.log failed for action=%s", action)
            return None
