"""KYCProfile now belongs to verification (see verification.0006). State only:
the table, its index and its rows stay exactly where they are."""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0021_userrestriction"),
        ("verification", "0006_kycprofile_owned_by_verification"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveIndex(
                    model_name="kycprofile",
                    name="kyc_status_idx",
                ),
                migrations.DeleteModel(
                    name="KYCProfile",
                ),
            ],
            database_operations=[],
        ),
    ]
