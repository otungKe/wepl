"""
Seed the canonical GL accounts (Chart of Accounts).

Idempotent and forward-only in effect: get_or_create on `code` means re-running
is a no-op. The reverse is intentionally a no-op — we never auto-delete
accounts, since lines may already reference them (PROTECT) and financial
reference data is not disposable.

The codes/names here MUST stay in sync with apps/ledger/coa.py. The logic is
duplicated (rather than imported) so this migration remains reproducible even if
coa.py changes later — a standard Django data-migration discipline.
"""
from django.db import migrations

GL_ACCOUNTS = [
    # (code, name, type)
    ('1000', 'M-Pesa Float / Settlement',    'ASSET'),
    ('1100', 'Suspense',                     'ASSET'),
    ('2000', 'Member Contributions Payable', 'LIABILITY'),
    ('2100', 'Welfare Payable',              'LIABILITY'),
    ('2200', 'Shares Payable',               'LIABILITY'),
    ('3000', 'Opening Balance Equity',       'EQUITY'),
    ('4000', 'Fee Revenue',                  'INCOME'),
]


def seed(apps, schema_editor):
    Account = apps.get_model('ledger', 'Account')
    for code, name, type_ in GL_ACCOUNTS:
        Account.objects.get_or_create(
            code=code, defaults={'name': name, 'type': type_},
        )


def unseed(apps, schema_editor):
    # Intentional no-op: financial reference data is not auto-deleted.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('ledger', '0003_journal_balance_trigger'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
