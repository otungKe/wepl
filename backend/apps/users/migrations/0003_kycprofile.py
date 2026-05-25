import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0002_user_name'),
    ]

    operations = [
        migrations.CreateModel(
            name='KYCProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('full_name', models.CharField(max_length=255)),
                ('id_number', models.CharField(max_length=20, unique=True)),
                ('date_of_birth', models.DateField()),
                ('email', models.EmailField(blank=True, default='', max_length=254)),
                ('id_front', models.ImageField(upload_to='kyc/ids/')),
                ('id_back', models.ImageField(blank=True, null=True, upload_to='kyc/ids/')),
                ('county', models.CharField(choices=[
                    ('Baringo', 'Baringo'), ('Bomet', 'Bomet'), ('Bungoma', 'Bungoma'),
                    ('Busia', 'Busia'), ('Elgeyo-Marakwet', 'Elgeyo-Marakwet'), ('Embu', 'Embu'),
                    ('Garissa', 'Garissa'), ('Homa Bay', 'Homa Bay'), ('Isiolo', 'Isiolo'),
                    ('Kajiado', 'Kajiado'), ('Kakamega', 'Kakamega'), ('Kericho', 'Kericho'),
                    ('Kiambu', 'Kiambu'), ('Kilifi', 'Kilifi'), ('Kirinyaga', 'Kirinyaga'),
                    ('Kisii', 'Kisii'), ('Kisumu', 'Kisumu'), ('Kitui', 'Kitui'),
                    ('Kwale', 'Kwale'), ('Laikipia', 'Laikipia'), ('Lamu', 'Lamu'),
                    ('Machakos', 'Machakos'), ('Makueni', 'Makueni'), ('Mandera', 'Mandera'),
                    ('Marsabit', 'Marsabit'), ('Meru', 'Meru'), ('Migori', 'Migori'),
                    ('Mombasa', 'Mombasa'), ("Murang'a", "Murang'a"), ('Nairobi', 'Nairobi'),
                    ('Nakuru', 'Nakuru'), ('Nandi', 'Nandi'), ('Narok', 'Narok'),
                    ('Nyamira', 'Nyamira'), ('Nyandarua', 'Nyandarua'), ('Nyeri', 'Nyeri'),
                    ('Samburu', 'Samburu'), ('Siaya', 'Siaya'), ('Taita-Taveta', 'Taita-Taveta'),
                    ('Tana River', 'Tana River'), ('Tharaka-Nithi', 'Tharaka-Nithi'),
                    ('Trans Nzoia', 'Trans Nzoia'), ('Turkana', 'Turkana'),
                    ('Uasin Gishu', 'Uasin Gishu'), ('Vihiga', 'Vihiga'),
                    ('Wajir', 'Wajir'), ('West Pokot', 'West Pokot'),
                ], max_length=50)),
                ('sub_county', models.CharField(blank=True, default='', max_length=100)),
                ('occupation', models.CharField(max_length=255)),
                ('source_of_income', models.CharField(choices=[
                    ('employment', 'Employment / Salary'),
                    ('business', 'Business / Self-employment'),
                    ('investment', 'Investment Returns'),
                    ('pension', 'Pension / Retirement'),
                    ('rental', 'Rental Income'),
                    ('remittance', 'Remittance from Abroad'),
                    ('farming', 'Farming / Agriculture'),
                    ('other', 'Other'),
                ], max_length=20)),
                ('expected_monthly_income', models.CharField(choices=[
                    ('under_250k', 'Up to KES 250,000 / month'),
                    ('250k_to_1m', 'KES 250,001 – 1,000,000 / month'),
                    ('above_1m', 'Above KES 1,000,000 / month'),
                ], max_length=20)),
                ('referral_code', models.CharField(blank=True, default='', max_length=50)),
                ('status', models.CharField(choices=[
                    ('pending', 'Pending Review'),
                    ('approved', 'Approved'),
                    ('rejected', 'Rejected'),
                ], default='pending', max_length=20)),
                ('rejection_reason', models.TextField(blank=True, default='')),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('submitted_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('reviewed_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='kyc_reviews',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('user', models.OneToOneField(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='kyc',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'indexes': [
                    models.Index(fields=['status'], name='kyc_status_idx'),
                ],
            },
        ),
    ]
