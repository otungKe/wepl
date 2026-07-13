"""Extend Row-Level Security to organizations_organization (ADR-0008 / C-1).

The Organization spine (ADR-0026) carries a ``tenant_id`` column, so it gets the
same DB-level isolation policy as every other tenant-columned table. Semantics
identical to 0003/0005/0006: visible/writable when no tenant is pinned (system
access), the row is shared (``tenant_id IS NULL``), or it matches the session's
``app.tenant_id``.
"""
from django.db import migrations

_POLICY = """
ALTER TABLE organizations_organization ENABLE ROW LEVEL SECURITY;
ALTER TABLE organizations_organization FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON organizations_organization
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
DROP POLICY IF EXISTS tenant_isolation ON organizations_organization;
ALTER TABLE organizations_organization NO FORCE ROW LEVEL SECURITY;
ALTER TABLE organizations_organization DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0006_rls_provider_event'),
        ('organizations', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(sql=_POLICY, reverse_sql=_DROP),
    ]
