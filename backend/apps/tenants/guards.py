"""Cross-tenant access guardrails (Phase 6, P6-05).

RLS blocks the ledger tables at the database. This guard covers app-level access
to tenant-owned aggregates (communities, funds) whose tables are not (yet) under
RLS: when a request is pinned to a tenant and tries to reach a resource owned by
a different tenant, the attempt is audited and refused.

System/staff contexts (no tenant pinned) are not restricted — they operate
across tenants by design.
"""
import logging

from django.core.exceptions import PermissionDenied

from .rls import current_tenant_id

logger = logging.getLogger(__name__)


def guard_tenant(resource_tenant_id, *, request=None, resource_type='', resource_id=None):
    """Refuse + audit access when the pinned tenant differs from the resource's.

    No-ops when no tenant is pinned (system/staff) or the resource is shared
    (resource_tenant_id is None).
    """
    current = current_tenant_id()
    if current is None or resource_tenant_id is None:
        return
    if resource_tenant_id == current:
        return

    user = getattr(request, 'user', None)
    from .models import CrossTenantAccessAttempt
    CrossTenantAccessAttempt.objects.create(
        user=user if getattr(user, 'is_authenticated', False) else None,
        current_tenant_id=current,
        resource_tenant_id=resource_tenant_id,
        resource_type=resource_type,
        resource_id=str(resource_id or ''),
        path=getattr(request, 'path', '')[:255] if request else '',
    )
    logger.warning("Blocked cross-tenant access: tenant=%s tried %s#%s (tenant=%s)",
                   current, resource_type, resource_id, resource_tenant_id)
    raise PermissionDenied("This resource belongs to a different organisation.")
