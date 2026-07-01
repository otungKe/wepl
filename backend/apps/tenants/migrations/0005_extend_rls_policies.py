"""Extend Postgres Row-Level Security to every remaining tenant-columned table
(ADR-0008 hardening; follow-up to 0003_rls_policies).

0003 enabled RLS on the two ledger tables only (``ledger_account``,
``ledger_financialtransaction``). Every other table that carries a real
``tenant_id`` column — communities, per-tenant limit rules, payment intents, the
audit log, and stored files — was left without a DB-level backstop, so a pinned
member request relied purely on application-layer scoping for those.

This migration applies the *same* isolation policy to them, so once
``app.tenant_id`` is set (member requests, or an explicit ``tenant_context``),
Postgres itself refuses cross-tenant reads/writes on these tables too.

Policy semantics are identical to 0003 and unchanged: a row is visible/writable
when no tenant context is set (system access — Celery/migrations/management
commands/platform reporting), or the row is shared (``tenant_id IS NULL``), or it
matches the session's ``app.tenant_id``. ``FORCE`` applies the policy to the table
owner too; superusers still bypass RLS by design, so deploy with a NON-superuser
DB role for isolation to bite.

Note: ``contributions`` funds (Contribution/WelfareFund/SharesFund) have no
``tenant_id`` column of their own (they inherit tenancy via their Community), so
they cannot carry a keyed RLS policy without a schema change and remain
application-scoped for now — see ADR-0008.
"""
from django.db import migrations

TABLES = (
    'communities_community',
    'controls_limitrule',
    'payments_paymentintent',
    'audit_auditevent',
    'files_storedfile',
)

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
        ('tenants', '0004_crosstenantaccessattempt'),
        ('communities', '0014_alter_community_tenant'),
        ('controls', '0003_limitrule_tenant'),
        ('payments', '0004_reconciliationdrift_paymentintent'),
        ('audit', '0001_initial'),
        ('files', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            sql='\n'.join(_POLICY.format(table=t) for t in TABLES),
            reverse_sql='\n'.join(_DROP.format(table=t) for t in TABLES),
        ),
    ]
