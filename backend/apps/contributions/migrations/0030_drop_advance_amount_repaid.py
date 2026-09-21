"""Drop EmergencyAdvance's mutable repayment counter (ADR-0002).

``amount_repaid`` was incremented in ``EmergencyAdvanceService.repay`` alongside
— but separately from — the journal that repayment posted, which is how it came
to double-count a replayed settlement callback (#201). It is now a property over
the advance's repayment journals.

No data migration. The journals already hold every repayment, so the figure the
column held is simply replaced by the correct one; where the two differ, the
column is the one that is wrong.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("contributions", "0029_derive_shareholding_from_ledger"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="emergencyadvance",
            name="amount_repaid",
        ),
    ]
