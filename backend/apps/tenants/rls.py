"""Row-Level-Security tenant context (Phase 6, P6-02, ADR-0008).

Postgres RLS policies isolate tenant rows based on the ``app.tenant_id`` session
GUC. These helpers set / clear it. When unset (empty), the policy is permissive —
system contexts (Celery tasks, migrations, management commands, webhooks) operate
across all tenants; a request that sets a tenant is restricted to it.

Note: RLS is bypassed for superusers and (without FORCE) table owners. The
migration uses ``FORCE ROW LEVEL SECURITY``; deploy the app with a NON-superuser
DB role for isolation to bite. Until per-user tenant wiring lands (P6-04), nothing
sets the context on web requests, so behaviour is unchanged in production.
"""
from contextlib import contextmanager

from django.db import connection


def set_current_tenant(tenant_id) -> None:
    """Pin the current tenant for this DB session (parameterised; SQL-safe)."""
    with connection.cursor() as cur:
        cur.execute("SELECT set_config('app.tenant_id', %s, false)", [str(tenant_id)])


def clear_current_tenant() -> None:
    """Clear the tenant context (back to permissive / system access)."""
    with connection.cursor() as cur:
        cur.execute("RESET app.tenant_id")


def current_tenant_id() -> int | None:
    """The tenant pinned for this session, or None when unset (system context)."""
    with connection.cursor() as cur:
        cur.execute("SELECT NULLIF(current_setting('app.tenant_id', true), '')")
        val = cur.fetchone()[0]
    return int(val) if val else None


@contextmanager
def tenant_context(tenant_id):
    """Scope a block to one tenant, always resetting afterwards.

        with tenant_context(t.id):
            ...  # only this tenant's rows are visible
    """
    set_current_tenant(tenant_id)
    try:
        yield
    finally:
        clear_current_tenant()
