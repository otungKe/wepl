"""Drop ShareHolding's mutable money counters (ADR-0002).

``shares_count`` and ``total_contributed`` were incremented alongside each
purchase, separately from the journal the purchase posted — the kind of mutable
balance the ledger core exists to make unnecessary. They are now properties
reading the member's shares sub-ledger.

No data migration accompanies this: the sub-ledger already holds every purchase,
so the figures the columns held (understated wherever a member bought more than
once, before the reset bug was fixed) are simply replaced by the correct ones.
The columns are dropped rather than backfilled because there is nothing left to
read them.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("contributions", "0028_poolactionrequest_poolactionapproval_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="shareholding",
            name="shares_count",
        ),
        migrations.RemoveField(
            model_name="shareholding",
            name="total_contributed",
        ),
    ]
