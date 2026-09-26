"""UserRestriction now belongs to controls (see controls.0006). State only: the
table, its indexes, its constraint and its rows stay where they are."""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0022_kycprofile_moved_to_verification"),
        ("controls", "0006_userrestriction_owned_by_controls"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveIndex(
                    model_name="userrestriction",
                    name="restriction_user_status_idx",
                ),
                migrations.RemoveIndex(
                    model_name="userrestriction",
                    name="restriction_kind_status_idx",
                ),
                migrations.RemoveConstraint(
                    model_name="userrestriction",
                    name="uniq_active_restriction_per_kind",
                ),
                migrations.DeleteModel(
                    name="UserRestriction",
                ),
            ],
            database_operations=[],
        ),
    ]
