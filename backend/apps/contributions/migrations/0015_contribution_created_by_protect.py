"""
P2-01: Change Contribution.created_by to PROTECT.

Prevents a user deletion from cascading into ALL financial data attached to
their created contributions (participants, transactions, disbursements,
advances, ledger entries).  Any code path that deletes a user with active
contributions will now raise ProtectedError, requiring explicit handling
(transfer ownership or archive contributions first).
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contributions', '0014_rename_contribution_community_active_idx_contrib_comm_active_idx_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='contribution',
            name='created_by',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='created_contributions',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
