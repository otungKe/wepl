"""Create a per-pool control account for every existing pool and re-parent that
pool's member sub-ledgers under it (ADR-0025 Part B).

Additive and history-safe: `parent` is a purely structural field (consumed
nowhere in posting/balances/reporting), so re-parenting rewrites no journal and
changes no balance. Pool balances remain the aggregate over member sub-ledgers.
"""
from django.db import migrations

# Pool fund types (member-liability) and their GL head. Advances (per-member
# receivables) are not pools and keep rolling up directly into 1200.
_POOL_GL = {"contribution": "2000", "welfare": "2100", "shares": "2200"}
POOL_WIDTH = 7


def create_pools(apps, schema_editor):
    from apps.core.ids import uuid7
    Account = apps.get_model("ledger", "Account")

    pools = (Account.objects
             .filter(owner__isnull=False, fund_type__in=_POOL_GL.keys(),
                     fund_id__isnull=False)
             .values("fund_type", "fund_id").distinct())

    for p in pools:
        ft, fid = p["fund_type"], p["fund_id"]
        gl = Account.objects.get(code=_POOL_GL[ft])
        pool, _ = Account.objects.get_or_create(
            owner=None, fund_type=ft, fund_id=fid,
            defaults={
                "code":        f"{_POOL_GL[ft]}-{int(fid):0{POOL_WIDTH}d}",
                "name":        f"Pool #{fid} · {ft} payable",
                "type":        gl.type,
                "parent_id":   gl.id,
                "account_uid": uuid7(),
            },
        )
        # Re-parent this pool's member sub-ledgers under the control account.
        Account.objects.filter(
            owner__isnull=False, fund_type=ft, fund_id=fid,
        ).exclude(pk=pool.pk).update(parent=pool)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [("ledger", "0013_account_ledger_acct_pool_uniq")]
    operations = [migrations.RunPython(create_pools, noop)]
