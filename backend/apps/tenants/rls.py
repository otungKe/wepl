"""Row-Level-Security tenant context (Phase 6, P6-02, ADR-0008).

Postgres RLS policies isolate tenant rows based on the ``app.tenant_id`` session
GUC. These helpers set / clear it. When unset (empty), the policy is permissive —
system contexts (Celery tasks, migrations, management commands, webhooks) operate
across all tenants; a request that sets a tenant is restricted to it.

RLS is enforced on every table that carries a ``tenant_id`` column:
``ledger_account`` and ``ledger_financialtransaction`` (migration 0003), and
``communities_community``, ``controls_limitrule``, ``payments_paymentintent``,
``audit_auditevent`` and ``files_storedfile`` (migration 0005), and
``payments_providerevent`` (migration 0006). Tables without a
``tenant_id`` column (e.g. contributions funds, which inherit tenancy via their
Community) stay application-scoped — see ADR-0008.

Note: RLS is bypassed for superusers and (without FORCE) table owners. The
migrations use ``FORCE ROW LEVEL SECURITY``; deploy the app with a NON-superuser
DB role for isolation to bite. ``TenantJWTAuthentication`` pins the context for
member web requests (P6-04); Celery ``task_prerun``/``task_postrun`` hooks
(``celery_hooks``) clear it at task boundaries so a pinned tenant never leaks onto
the next task on a pooled connection.
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
