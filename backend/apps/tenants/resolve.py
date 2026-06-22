"""Tenant resolution helpers (Phase 6).

Until tenants are provisioned and users mapped (P6-04), everything resolves to
the single default tenant. These helpers centralise that logic so call sites are
already tenant-correct and the wiring can deepen without touching them.
"""
from .models import DEFAULT_TENANT_SLUG, Tenant


def default_tenant() -> Tenant:
    """The platform's default tenant (created by migration/seed). Get-or-create
    so it is always available even in a fresh test database."""
    tenant, _ = Tenant.objects.get_or_create(
        slug=DEFAULT_TENANT_SLUG, defaults={'name': 'Default'},
    )
    return tenant


def tenant_for_user(user) -> Tenant:
    """Resolve the tenant a user belongs to. Today: the default tenant.

    P6-04 will derive this from the user's institution membership; keeping the
    seam here means call sites do not change when that lands.
    """
    return default_tenant()


def tenant_for_community(community) -> Tenant:
    """The tenant that owns a community (falls back to default)."""
    return getattr(community, 'tenant', None) or default_tenant()
