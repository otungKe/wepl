import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("communities", "0009_add_category_location"),
    ]

    operations = [
        # Protect a creator's communities (and their financial history) from
        # cascade-deletion when a user account is removed.
        migrations.AlterField(
            model_name="community",
            name="created_by",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="created_communities",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddIndex(
            model_name="community",
            index=models.Index(
                fields=["is_private", "category"],
                name="community_priv_cat_idx",
            ),
        ),
    ]
