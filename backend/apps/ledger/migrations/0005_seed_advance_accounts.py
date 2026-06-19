"""
Seed the GL accounts introduced for emergency-advance accounting (P0-04):

    1200  ASSET   Advances Receivable
    4100  INCOME  Interest Income

Same discipline as 0004: idempotent get_or_create on `code`, list duplicated
(not imported from coa.py) so the migration stays reproducible. Reverse is a
no-op — financial reference data is never auto-deleted.
"""
from django.db import migrations

NEW_ACCOUNTS = [
    # (code, name, type)
    ('1200', 'Advances Receivable', 'ASSET'),
    ('4100', 'Interest Income',     'INCOME'),
]


def seed(apps, schema_editor):
    Account = apps.get_model('ledger', 'Account')
    for code, name, type_ in NEW_ACCOUNTS:
        Account.objects.get_or_create(
            code=code, defaults={'name': name, 'type': type_},
        )


def unseed(apps, schema_editor):
    # Intentional no-op: financial reference data is not auto-deleted.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('ledger', '0004_seed_chart_of_accounts'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
