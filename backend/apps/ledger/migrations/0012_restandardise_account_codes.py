"""Restandardise sub-ledger account codes to the canonical GL-anchored, fixed-
width form (ADR-0025), e.g. ``2000-0000018-000000055``.

Safe because the code is mutable metadata: journals reference ``Account.id`` and
resolution keys on ``(owner, fund_type, fund_id)`` — renaming codes rewrites no
history and breaks no lookup. Self-contained (no import of app code that may
evolve).
"""
from django.db import migrations

# GL head each sub-ledger fund_type hangs off — the code prefix.
_FUND_GL = {
    "contribution": "2000",
    "welfare":      "2100",
    "shares":       "2200",
    "advance":      "1200",
}
POOL_WIDTH = 7
MEMBER_WIDTH = 9


def restandardise(apps, schema_editor):
    Account = apps.get_model("ledger", "Account")
    for acct in Account.objects.filter(owner__isnull=False).iterator():
        gl = _FUND_GL.get(acct.fund_type)
        if not gl or acct.fund_id is None:
            continue
        new_code = f"{gl}-{int(acct.fund_id):0{POOL_WIDTH}d}-{int(acct.owner_id):0{MEMBER_WIDTH}d}"
        if acct.code != new_code:
            acct.code = new_code
            acct.save(update_fields=["code"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [("ledger", "0011_backfill_account_uid")]
    operations = [migrations.RunPython(restandardise, noop)]
