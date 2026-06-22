"""Create the default tenant and backfill existing communities + financial rows.

Additive rollout (ADR-0008): existing single-tenant data is assigned to one
'default' tenant so the column is populated everywhere before any later
NOT NULL / RLS step.
"""
from django.db import migrations


def forwards(apps, schema_editor):
    Tenant = apps.get_model('tenants', 'Tenant')
    tenant, _ = Tenant.objects.get_or_create(slug='default', defaults={'name': 'Default'})

    Community = apps.get_model('communities', 'Community')
    Community.objects.filter(tenant__isnull=True).update(tenant=tenant)

    Account = apps.get_model('ledger', 'Account')
    Account.objects.filter(tenant__isnull=True).update(tenant=tenant)

    FinancialTransaction = apps.get_model('ledger', 'FinancialTransaction')
    FinancialTransaction.objects.filter(tenant__isnull=True).update(tenant=tenant)


def backwards(apps, schema_editor):
    # Non-destructive reverse: leave rows pointing at the default tenant; only
    # the Tenant row would be removed if no longer referenced. We no-op to avoid
    # PROTECT violations.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0001_initial'),
        ('communities', '0013_community_tenant'),
        ('ledger', '0008_account_tenant_financialtransaction_tenant'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
