"""
Database-level enforcement of the double-entry invariant.

A DEFERRABLE INITIALLY DEFERRED constraint trigger re-sums each journal's lines
at COMMIT and aborts the transaction if they are unbalanced or number fewer than
two. Because it is deferred, the writer can legitimately insert lines one-by-one
within a transaction; the check only runs once, at commit, when the journal is
complete.

This guarantees the invariant even against raw SQL, a future buggy service, or
a direct DB session — the app-layer check in posting.post_journal() is the
convenient guard, this is the last line of defence.

PostgreSQL-specific (plpgsql). The project runs PostgreSQL in every environment.
"""
from django.db import migrations


CREATE = r"""
CREATE OR REPLACE FUNCTION ledger_assert_journal_balanced()
RETURNS trigger AS $$
DECLARE
    v_journal_id bigint;
    v_debit  numeric(20,4);
    v_credit numeric(20,4);
    v_count  integer;
BEGIN
    v_journal_id := COALESCE(NEW.journal_id, OLD.journal_id);

    SELECT
        COALESCE(SUM(amount) FILTER (WHERE direction = 'DEBIT'),  0),
        COALESCE(SUM(amount) FILTER (WHERE direction = 'CREDIT'), 0),
        COUNT(*)
    INTO v_debit, v_credit, v_count
    FROM ledger_journalline
    WHERE journal_id = v_journal_id;

    -- A journal with zero remaining lines is ignored (nothing to validate).
    IF v_count > 0 THEN
        IF v_count < 2 THEN
            RAISE EXCEPTION
                'Journal % must have at least two lines (found %)',
                v_journal_id, v_count
                USING ERRCODE = 'check_violation';
        END IF;
        IF v_debit <> v_credit THEN
            RAISE EXCEPTION
                'Journal % is unbalanced: debit=% credit=%',
                v_journal_id, v_debit, v_credit
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;

    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE CONSTRAINT TRIGGER ledger_journalline_balanced
    AFTER INSERT OR UPDATE OR DELETE ON ledger_journalline
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW
    EXECUTE FUNCTION ledger_assert_journal_balanced();
"""

DROP = r"""
DROP TRIGGER IF EXISTS ledger_journalline_balanced ON ledger_journalline;
DROP FUNCTION IF EXISTS ledger_assert_journal_balanced();
"""


class Migration(migrations.Migration):

    dependencies = [
        ('ledger', '0002_double_entry_core'),
    ]

    operations = [
        migrations.RunSQL(sql=CREATE, reverse_sql=DROP),
    ]
