"""UserRestriction moves from users to controls — the class, not the table.

State only: ``users_userrestriction`` keeps its name, rows, indexes and the
one-active-per-kind constraint. The content type row is relabelled so admin
permissions follow the model. ``users.0023`` drops it from users' state.
"""

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


def relabel_content_type(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    if ContentType.objects.filter(app_label="controls", model="userrestriction").exists():
        return
    ContentType.objects.filter(app_label="users", model="userrestriction").update(
        app_label="controls")


def relabel_content_type_back(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    if ContentType.objects.filter(app_label="users", model="userrestriction").exists():
        return
    ContentType.objects.filter(app_label="controls", model="userrestriction").update(
        app_label="users")


class Migration(migrations.Migration):

    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        ("users", "0022_kycprofile_moved_to_verification"),
        ("controls", "0005_alter_limitrule_op_type"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="UserRestriction",
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
                                    ("login", "Suspend login"),
                                    ("payout", "Block money out (withdrawals / transfers)"),
                                    ("payin", "Block money in (deposits)"),
                                    ("freeze", "Freeze all money movement"),
                                    ("community_create", "Restrict community creation"),
                                    ("community_admin", "Restrict community administration"),
                                ],
                                max_length=20,
                            ),
                        ),
                        (
                            "status",
                            models.CharField(
                                choices=[
                                    ("active", "Active"),
                                    ("lifted", "Lifted"),
                                    ("expired", "Expired"),
                                ],
                                db_index=True,
                                default="active",
                                max_length=10,
                            ),
                        ),
                        ("reason", models.TextField()),
                        (
                            "effective_at",
                            models.DateTimeField(default=django.utils.timezone.now),
                        ),
                        ("expires_at", models.DateTimeField(blank=True, null=True)),
                        (
                            "applied_by_label",
                            models.CharField(blank=True, default="", max_length=120),
                        ),
                        (
                            "approval_ref",
                            models.CharField(blank=True, default="", max_length=64),
                        ),
                        ("lifted_at", models.DateTimeField(blank=True, null=True)),
                        (
                            "lifted_by_label",
                            models.CharField(blank=True, default="", max_length=120),
                        ),
                        ("lift_reason", models.TextField(blank=True, default="")),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        (
                            "user",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="restrictions",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                    ],
                    options={
                        "db_table": "users_userrestriction",
                        "ordering": ("-created_at",),
                        "indexes": [
                            models.Index(
                                fields=["user", "status"], name="restriction_user_status_idx"
                            ),
                            models.Index(
                                fields=["kind", "status"], name="restriction_kind_status_idx"
                            ),
                        ],
                        "constraints": [
                            models.UniqueConstraint(
                                condition=models.Q(("status", "active")),
                                fields=("user", "kind"),
                                name="uniq_active_restriction_per_kind",
                            )
                        ],
                    },
                ),
            ],
            database_operations=[],
        ),
        migrations.RunPython(relabel_content_type, relabel_content_type_back),
    ]
