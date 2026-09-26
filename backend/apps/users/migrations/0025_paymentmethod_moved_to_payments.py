"""PaymentMethod now belongs to payments (see payments.0011). State only: the
table, its index and its rows stay where they are."""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0024_verificationrequest_moved_to_verification"),
        ("payments", "0011_paymentmethod_owned_by_payments"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveIndex(
                    model_name="paymentmethod",
                    name="paymethod_user_default_idx",
                ),
                migrations.DeleteModel(
                    name="PaymentMethod",
                ),
            ],
            database_operations=[],
        ),
    ]
