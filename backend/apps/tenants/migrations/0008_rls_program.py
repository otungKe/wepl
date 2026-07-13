"""Extend Row-Level Security to organizations_program (ADR-0008 / C-1).

The Program spine (ADR-0026) carries a ``tenant_id`` column, so it gets the same
DB-level isolation policy as every other tenant-columned table. Semantics
identical to 0003/0005/0006/0007.
"""
from django.db import migrations

_POLICY = """
ALTER TABLE organizations_program ENABLE ROW LEVEL SECURITY;
ALTER TABLE organizations_program FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON organizations_program
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
DROP POLICY IF EXISTS tenant_isolation ON organizations_program;
ALTER TABLE organizations_program NO FORCE ROW LEVEL SECURITY;
ALTER TABLE organizations_program DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0007_rls_organization'),
        ('organizations', '0002_program'),
    ]

    operations = [
        migrations.RunSQL(sql=_POLICY, reverse_sql=_DROP),
    ]
