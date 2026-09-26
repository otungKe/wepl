"""KYCProfile moves from users to verification — the class, not the table.

State only: ``users_kycprofile`` keeps its name, rows, index and constraints,
and ``VerificationCase.kyc`` keeps pointing at the same table. The content type
row is relabelled so the model's admin permissions (and any group holding
them) follow it. ``users.0022`` drops the model from users' state.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def relabel_content_type(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    if ContentType.objects.filter(app_label="verification", model="kycprofile").exists():
        return
    ContentType.objects.filter(app_label="users", model="kycprofile").update(
        app_label="verification")


def relabel_content_type_back(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    if ContentType.objects.filter(app_label="users", model="kycprofile").exists():
        return
    ContentType.objects.filter(app_label="verification", model="kycprofile").update(
        app_label="users")


class Migration(migrations.Migration):

    dependencies = [
        ("verification", "0005_verificationcase_subject_id_and_more"),
        ("users", "0021_userrestriction"),
        ("contenttypes", "0002_remove_content_type_name"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="KYCProfile",
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
                        ("given_names", models.CharField(max_length=150)),
                        ("surname", models.CharField(default="", max_length=100)),
                        ("id_number", models.CharField(max_length=20, unique=True)),
                        ("date_of_birth", models.DateField()),
                        ("email", models.EmailField(blank=True, default="", max_length=254)),
                        ("kra_pin", models.CharField(blank=True, default="", max_length=11)),
                        ("id_front", models.ImageField(upload_to="kyc/ids/")),
                        (
                            "id_back",
                            models.ImageField(blank=True, null=True, upload_to="kyc/ids/"),
                        ),
                        (
                            "selfie",
                            models.ImageField(blank=True, null=True, upload_to="kyc/selfies/"),
                        ),
                        (
                            "county",
                            models.CharField(
                                choices=[
                                    ("Baringo", "Baringo"),
                                    ("Bomet", "Bomet"),
                                    ("Bungoma", "Bungoma"),
                                    ("Busia", "Busia"),
                                    ("Elgeyo-Marakwet", "Elgeyo-Marakwet"),
                                    ("Embu", "Embu"),
                                    ("Garissa", "Garissa"),
                                    ("Homa Bay", "Homa Bay"),
                                    ("Isiolo", "Isiolo"),
                                    ("Kajiado", "Kajiado"),
                                    ("Kakamega", "Kakamega"),
                                    ("Kericho", "Kericho"),
                                    ("Kiambu", "Kiambu"),
                                    ("Kilifi", "Kilifi"),
                                    ("Kirinyaga", "Kirinyaga"),
                                    ("Kisii", "Kisii"),
                                    ("Kisumu", "Kisumu"),
                                    ("Kitui", "Kitui"),
                                    ("Kwale", "Kwale"),
                                    ("Laikipia", "Laikipia"),
                                    ("Lamu", "Lamu"),
                                    ("Machakos", "Machakos"),
                                    ("Makueni", "Makueni"),
                                    ("Mandera", "Mandera"),
                                    ("Marsabit", "Marsabit"),
                                    ("Meru", "Meru"),
                                    ("Migori", "Migori"),
                                    ("Mombasa", "Mombasa"),
                                    ("Murang'a", "Murang'a"),
                                    ("Nairobi", "Nairobi"),
                                    ("Nakuru", "Nakuru"),
                                    ("Nandi", "Nandi"),
                                    ("Narok", "Narok"),
                                    ("Nyamira", "Nyamira"),
                                    ("Nyandarua", "Nyandarua"),
                                    ("Nyeri", "Nyeri"),
                                    ("Samburu", "Samburu"),
                                    ("Siaya", "Siaya"),
                                    ("Taita-Taveta", "Taita-Taveta"),
                                    ("Tana River", "Tana River"),
                                    ("Tharaka-Nithi", "Tharaka-Nithi"),
                                    ("Trans Nzoia", "Trans Nzoia"),
                                    ("Turkana", "Turkana"),
                                    ("Uasin Gishu", "Uasin Gishu"),
                                    ("Vihiga", "Vihiga"),
                                    ("Wajir", "Wajir"),
                                    ("West Pokot", "West Pokot"),
                                ],
                                max_length=50,
                            ),
                        ),
                        ("physical_address", models.CharField(default="", max_length=255)),
                        ("occupation", models.CharField(max_length=255)),
                        (
                            "source_of_income",
                            models.CharField(
                                choices=[
                                    ("employment", "Employment / Salary"),
                                    ("business", "Business / Self-employment"),
                                    ("investment", "Investment Returns"),
                                    ("pension", "Pension / Retirement"),
                                    ("rental", "Rental Income"),
                                    ("remittance", "Remittance from Abroad"),
                                    ("farming", "Farming / Agriculture"),
                                    ("other", "Other"),
                                ],
                                max_length=20,
                            ),
                        ),
                        (
                            "expected_monthly_income",
                            models.CharField(
                                choices=[
                                    ("under_250k", "Up to KES 250,000 / month"),
                                    ("250k_to_1m", "KES 250,001 – 1,000,000 / month"),
                                    ("above_1m", "Above KES 1,000,000 / month"),
                                ],
                                max_length=20,
                            ),
                        ),
                        (
                            "referral_code",
                            models.CharField(blank=True, default="", max_length=50),
                        ),
                        (
                            "status",
                            models.CharField(
                                choices=[
                                    ("pending", "Pending Review"),
                                    ("approved", "Approved"),
                                    ("rejected", "Rejected"),
                                ],
                                default="pending",
                                max_length=20,
                            ),
                        ),
                        ("rejection_reason", models.TextField(blank=True, default="")),
                        ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                        (
                            "verification_provider",
                            models.CharField(blank=True, default="", max_length=40),
                        ),
                        (
                            "verification_ref",
                            models.CharField(blank=True, default="", max_length=128),
                        ),
                        (
                            "verification_state",
                            models.CharField(blank=True, default="", max_length=20),
                        ),
                        ("verification_detail", models.JSONField(blank=True, default=dict)),
                        (
                            "verification_checked_at",
                            models.DateTimeField(blank=True, null=True),
                        ),
                        ("email_verified", models.BooleanField(default=False)),
                        (
                            "email_verification_token",
                            models.CharField(blank=True, default="", max_length=64),
                        ),
                        (
                            "email_verification_sent_at",
                            models.DateTimeField(blank=True, null=True),
                        ),
                        ("resubmission_requested", models.JSONField(blank=True, default=list)),
                        ("submitted_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        (
                            "reviewed_by",
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="kyc_reviews",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                        (
                            "user",
                            models.OneToOneField(
                                on_delete=django.db.models.deletion.PROTECT,
                                related_name="kyc",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                    ],
                    options={
                        "db_table": "users_kycprofile",
                    },
                ),
                migrations.AlterField(
                    model_name="verificationcase",
                    name="kyc",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="cases",
                        to="verification.kycprofile",
                    ),
                ),
                migrations.AddIndex(
                    model_name="kycprofile",
                    index=models.Index(fields=["status"], name="kyc_status_idx"),
                ),
            ],
            database_operations=[],
        ),
        migrations.RunPython(relabel_content_type, relabel_content_type_back),
    ]
