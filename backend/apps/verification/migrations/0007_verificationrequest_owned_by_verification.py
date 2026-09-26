"""VerificationRequest moves from users to verification — the class, not the table.

State only: ``users_verificationrequest`` keeps its name, rows and index. The
content type row is relabelled so admin permissions follow the model.
``users.0024`` drops it from users' state.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def relabel_content_type(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    if ContentType.objects.filter(app_label="verification", model="verificationrequest").exists():
        return
    ContentType.objects.filter(app_label="users", model="verificationrequest").update(
        app_label="verification")


def relabel_content_type_back(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    if ContentType.objects.filter(app_label="users", model="verificationrequest").exists():
        return
    ContentType.objects.filter(app_label="verification", model="verificationrequest").update(
        app_label="users")


class Migration(migrations.Migration):

    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        ("users", "0023_userrestriction_moved_to_controls"),
        ("verification", "0006_kycprofile_owned_by_verification"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="VerificationRequest",
                    fields=[
                        (
                            "id",
                            models.BigAutoField(
                                auto_created=True,
                                primary_key=True,
                                serialize=False,
                                verbose_name="ID",
                            ),
                        ),
                        (
                            "kind",
                            models.CharField(
                                choices=[
                                    ("transaction_docs", "Transaction supporting documents"),
                                    ("address_proof", "Proof of address"),
                                    ("kyc_supplement", "Additional KYC information"),
                                    ("clarification", "Clarification"),
                                    ("other", "Other"),
                                ],
                                default="other",
                                max_length=24,
                            ),
                        ),
                        ("title", models.CharField(max_length=140)),
                        (
                            "detail",
                            models.TextField(
                                help_text="What the user is being asked to provide."
                            ),
                        ),
                        (
                            "status",
                            models.CharField(
                                choices=[
                                    ("open", "Awaiting your response"),
                                    ("submitted", "Submitted — under review"),
                                    ("resolved", "Resolved"),
                                ],
                                default="open",
                                max_length=12,
                            ),
                        ),
                        ("response_note", models.TextField(blank=True, default="")),
                        (
                            "document",
                            models.FileField(
                                blank=True, null=True, upload_to="verification/requests/"
                            ),
                        ),
                        ("review_note", models.TextField(blank=True, default="")),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("responded_at", models.DateTimeField(blank=True, null=True)),
                        ("resolved_at", models.DateTimeField(blank=True, null=True)),
                        (
                            "case",
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="customer_requests",
                                to="verification.verificationcase",
                            ),
                        ),
                        (
                            "created_by",
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="verification_requests_created",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                        (
                            "user",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="verification_requests",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                    ],
                    options={
                        "db_table": "users_verificationrequest",
                        "ordering": ["-created_at"],
                        "indexes": [
                            models.Index(
                                fields=["user", "status"], name="verifreq_user_status_idx"
                            )
                        ],
                    },
                ),
            ],
            database_operations=[],
        ),
        migrations.RunPython(relabel_content_type, relabel_content_type_back),
    ]
