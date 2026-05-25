import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('contributions', '0002_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='MpesaSTKRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('phone_number', models.CharField(max_length=20)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('checkout_request_id', models.CharField(max_length=255, unique=True)),
                ('merchant_request_id', models.CharField(max_length=255)),
                ('status', models.CharField(
                    choices=[('PENDING', 'Pending'), ('SUCCESS', 'Success'), ('FAILED', 'Failed')],
                    default='PENDING', max_length=20,
                )),
                ('result_code', models.IntegerField(blank=True, null=True)),
                ('result_desc', models.TextField(blank=True, null=True)),
                ('mpesa_receipt', models.CharField(blank=True, max_length=50, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('contribution', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='stk_requests',
                    to='contributions.contribution',
                )),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='stk_requests',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
        ),
        migrations.CreateModel(
            name='MpesaC2BTransaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('phone_number', models.CharField(max_length=20)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('mpesa_receipt', models.CharField(max_length=50, unique=True)),
                ('transaction_date', models.DateTimeField()),
                ('bill_ref_number', models.CharField(max_length=255)),
                ('is_reconciled', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('contribution', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='mpesa_transactions',
                    to='contributions.contribution',
                )),
                ('user', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='mpesa_transactions',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
        ),
    ]
