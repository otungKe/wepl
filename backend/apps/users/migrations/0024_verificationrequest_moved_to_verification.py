"""VerificationRequest now belongs to verification (see verification.0007). State
only: the table, its index and its rows stay where they are."""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0023_userrestriction_moved_to_controls"),
        ("verification", "0007_verificationrequest_owned_by_verification"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveIndex(
                    model_name="verificationrequest",
                    name="verifreq_user_status_idx",
                ),
                migrations.DeleteModel(
                    name="VerificationRequest",
                ),
            ],
            database_operations=[],
        ),
    ]
