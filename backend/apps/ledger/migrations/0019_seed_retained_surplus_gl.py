"""
Seed the Retained Surplus GL head (3200, EQUITY) — ADR-0027.

Pool-level collective surplus (external income before distribution) rolls up into
this head via owner-less ``3200-<fund_id>`` control accounts. Idempotent
get_or_create on ``code``; the reverse is a deliberate no-op (financial reference
data is never auto-deleted). Kept in sync with apps/ledger/coa.py, logic
duplicated per data-migration discipline.
"""
from django.db import migrations


def seed(apps, schema_editor):
    Account = apps.get_model('ledger', 'Account')
    Account.objects.get_or_create(
        code='3200', defaults={'name': 'Retained Surplus', 'type': 'EQUITY'},
    )


def unseed(apps, schema_editor):
    # Intentional no-op: financial reference data is not auto-deleted.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('ledger', '0018_alter_financialtransaction_op_type'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
