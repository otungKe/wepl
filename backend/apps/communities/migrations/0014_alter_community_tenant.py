"""Make Community.tenant mandatory (Phase 6, P6-05).

All rows were backfilled to the default tenant (tenants 0002) and new communities
are stamped on create, so the column has no nulls — the ALTER ... SET NOT NULL is
safe without a one-off default.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0002_default_tenant_backfill'),
        ('communities', '0013_community_tenant'),
    ]

    operations = [
        migrations.AlterField(
            model_name='community',
            name='tenant',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='communities',
                to='tenants.tenant',
            ),
        ),
    ]
