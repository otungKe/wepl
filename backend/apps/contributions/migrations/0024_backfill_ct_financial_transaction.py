"""Backfill ContributionTransaction.financial_transaction by shared M-Pesa receipt.

Historical rows predate the FK; both records carry the same mpesa_receipt, so we
match on it to unify the reference retroactively.
"""
from django.db import migrations


def backfill(apps, schema_editor):
    ContributionTransaction = apps.get_model("contributions", "ContributionTransaction")
    FinancialTransaction = apps.get_model("ledger", "FinancialTransaction")

    receipts = (ContributionTransaction.objects
                .filter(financial_transaction__isnull=True)
                .exclude(mpesa_receipt__isnull=True)
                .exclude(mpesa_receipt="")
                .values_list("mpesa_receipt", flat=True)
                .distinct())

    ft_by_receipt = {
        ft.mpesa_receipt: ft.id
        for ft in FinancialTransaction.objects.filter(mpesa_receipt__in=list(receipts))
    }
    for ct in (ContributionTransaction.objects
               .filter(financial_transaction__isnull=True)
               .exclude(mpesa_receipt__isnull=True)
               .iterator()):
        ft_id = ft_by_receipt.get(ct.mpesa_receipt)
        if ft_id:
            ct.financial_transaction_id = ft_id
            ct.save(update_fields=["financial_transaction"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("contributions", "0023_contributiontransaction_financial_transaction"),
        ("ledger", "0001_initial"),
    ]
    operations = [migrations.RunPython(backfill, noop)]
