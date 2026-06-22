"""Enable Postgres Row-Level Security on the tenant-scoped financial tables
(Phase 6, P6-02, ADR-0008).

Policy: a row is visible/writable when no tenant context is set (system access),
or the row is shared (tenant_id IS NULL), or it matches the session's
``app.tenant_id``. ``RESET`` leaves the GUC as '' so we treat '' as unset via
NULLIF. FORCE makes the policy apply to the table owner too (not just other
roles); superusers still bypass RLS by design.
"""
from django.db import migrations

TABLES = ('ledger_account', 'ledger_financialtransaction')

_POLICY = """
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON {table}
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
DROP POLICY IF EXISTS tenant_isolation ON {table};
ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;
ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0002_default_tenant_backfill'),
        ('ledger', '0008_account_tenant_financialtransaction_tenant'),
    ]

    operations = [
        migrations.RunSQL(
            sql='\n'.join(_POLICY.format(table=t) for t in TABLES),
            reverse_sql='\n'.join(_DROP.format(table=t) for t in TABLES),
        ),
    ]
