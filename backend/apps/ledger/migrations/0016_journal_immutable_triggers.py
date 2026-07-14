"""Database-level enforcement of ledger immutability.

The ledger is append-only by design: a posted JournalEntry / JournalLine is never
edited or deleted — corrections are always *new* reversing entries (models.py).
That invariant was previously guarded only in Python (the `save()`/`delete()`
overrides that raise JournalImmutableError). Those overrides are bypassed by
anything that doesn't route through a model instance — `QuerySet.update()`,
`QuerySet.delete()`, `bulk_update`, raw SQL, or a direct psql session.

This installs BEFORE UPDATE OR DELETE triggers on both journal tables so the
immutability invariant holds against every writer, not just the ORM instance
path — the same "last line of defence" posture as the balance trigger (0003).
INSERTs are untouched, so `post_journal()`'s bulk_create still works.

PostgreSQL-specific (plpgsql). The project runs PostgreSQL in every environment.
"""
from django.db import migrations


CREATE = r"""
CREATE OR REPLACE FUNCTION ledger_forbid_mutation()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION
        'ledger %.% is immutable: % is not permitted — post a reversing entry instead.',
        TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER ledger_journalentry_immutable
    BEFORE UPDATE OR DELETE ON ledger_journalentry
    FOR EACH ROW EXECUTE FUNCTION ledger_forbid_mutation();

CREATE TRIGGER ledger_journalline_immutable
    BEFORE UPDATE OR DELETE ON ledger_journalline
    FOR EACH ROW EXECUTE FUNCTION ledger_forbid_mutation();
"""

DROP = r"""
DROP TRIGGER IF EXISTS ledger_journalentry_immutable ON ledger_journalentry;
DROP TRIGGER IF EXISTS ledger_journalline_immutable ON ledger_journalline;
DROP FUNCTION IF EXISTS ledger_forbid_mutation();
"""


class Migration(migrations.Migration):

    dependencies = [
        ('ledger', '0015_financialtransaction_counterparty_name'),
    ]

    operations = [
        migrations.RunSQL(sql=CREATE, reverse_sql=DROP),
    ]
