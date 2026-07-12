"""Extend Row-Level Security to payments_providerevent (ADR-0008).

ProviderEvent (the append-only raw provider-callback log) was added with a
``tenant_id`` column stamped from its PaymentIntent, so it must carry the same
DB-level isolation as every other tenant-columned table. Policy semantics are
identical to 0003/0005: visible/writable when no tenant is pinned (system access
— Celery/migrations/webhooks/platform reporting), the row is shared
(``tenant_id IS NULL``), or it matches ``app.tenant_id``.
"""
from django.db import migrations

_POLICY = """
ALTER TABLE payments_providerevent ENABLE ROW LEVEL SECURITY;
ALTER TABLE payments_providerevent FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON payments_providerevent
  USING (
    NULLIF(current_setting('app.tenant_id', true), '') IS NULL
    OR tenant_id IS NULL
    OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::integer
  )
  WITH CHECK (
    NULLIF(current_setting('app.tenant_id', true), '') IS NULL
    OR tenant_id IS NULL
    OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::integer
  );
"""

_DROP = """
DROP POLICY IF EXISTS tenant_isolation ON payments_providerevent;
ALTER TABLE payments_providerevent NO FORCE ROW LEVEL SECURITY;
ALTER TABLE payments_providerevent DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0005_extend_rls_policies'),
        ('payments', '0007_providerevent_tenant'),
    ]

    operations = [
        migrations.RunSQL(sql=_POLICY, reverse_sql=_DROP),
    ]
