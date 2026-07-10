"""Backfill account_uid (UUIDv7) for every existing Account (ADR-0025)."""
from django.db import migrations


def backfill(apps, schema_editor):
    from apps.core.ids import uuid7
    Account = apps.get_model("ledger", "Account")
    for acct in Account.objects.filter(account_uid__isnull=True).iterator():
        acct.account_uid = uuid7()
        acct.save(update_fields=["account_uid"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [("ledger", "0010_account_account_uid_alter_account_code_and_more")]
    operations = [migrations.RunPython(backfill, noop)]
