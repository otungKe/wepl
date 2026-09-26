"""PaymentMethod moves from users to payments — the class, not the table.

State only: ``users_paymentmethod`` keeps its name, rows and index. The content
type row is relabelled so admin permissions follow the model. ``users.0025``
drops it from users' state.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def relabel_content_type(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    if ContentType.objects.filter(app_label="payments", model="paymentmethod").exists():
        return
    ContentType.objects.filter(app_label="users", model="paymentmethod").update(
        app_label="payments")


def relabel_content_type_back(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    if ContentType.objects.filter(app_label="users", model="paymentmethod").exists():
        return
    ContentType.objects.filter(app_label="payments", model="paymentmethod").update(
        app_label="users")


class Migration(migrations.Migration):

    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        ("users", "0024_verificationrequest_moved_to_verification"),
        ("payments", "0010_backfill_collection_purpose"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="PaymentMethod",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                                   serialize=False, verbose_name="ID")),
                        ("kind", models.CharField(
                            choices=[("mpesa", "M-Pesa"), ("card", "Debit or credit card"),
                                     ("bank", "Bank account")],
                            max_length=8)),
                        ("label", models.CharField(blank=True, default="", max_length=60)),
                        ("is_default", models.BooleanField(default=False)),
                        ("status", models.CharField(
                            choices=[("active", "Active"), ("unavailable", "Coming soon")],
                            default="active", max_length=12)),
                        ("mpesa_phone", models.CharField(blank=True, default="", max_length=15)),
                        ("card_brand", models.CharField(blank=True, default="", max_length=20)),
                        ("card_last4", models.CharField(blank=True, default="", max_length=4)),
                        ("card_exp", models.CharField(blank=True, default="", max_length=5)),
                        ("bank_name", models.CharField(blank=True, default="", max_length=60)),
                        ("bank_account_last4", models.CharField(blank=True, default="", max_length=4)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("user", models.ForeignKey(
                            on_delete=django.db.models.deletion.CASCADE,
                            related_name="payment_methods",
                            to=settings.AUTH_USER_MODEL)),
                    ],
                    options={
                        "db_table": "users_paymentmethod",
                        "ordering": ["-is_default", "-created_at"],
                        "indexes": [models.Index(fields=["user", "is_default"],
                                                 name="paymethod_user_default_idx")],
                    },
                ),
            ],
            database_operations=[],
        ),
        migrations.RunPython(relabel_content_type, relabel_content_type_back),
    ]
