import django.db.models.deletion
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('communities', '0002_initial'),
        ('contributions', '0003_new_features'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── New Contribution fields ────────────────────────────────────────────
        migrations.AddField(
            model_name='contribution',
            name='tenure_type',
            field=models.CharField(
                choices=[('open', 'Open (no end date)'), ('date', 'Until a specific date'), ('period', 'Fixed period')],
                default='open', max_length=10,
            ),
        ),
        migrations.AddField(
            model_name='contribution',
            name='end_date',
            field=models.DateField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='contribution',
            name='period_months',
            field=models.PositiveIntegerField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='contribution',
            name='frequency',
            field=models.CharField(
                choices=[('daily', 'Daily'), ('weekly', 'Weekly'), ('monthly', 'Monthly'), ('anytime', 'Anytime')],
                default='anytime', max_length=10,
            ),
        ),
        migrations.AddField(
            model_name='contribution',
            name='amount_type',
            field=models.CharField(
                choices=[('fixed', 'Fixed amount per member'), ('open', 'Open (any amount)')],
                default='open', max_length=10,
            ),
        ),
        migrations.AddField(
            model_name='contribution',
            name='fixed_amount',
            field=models.DecimalField(decimal_places=2, max_digits=12, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='contribution',
            name='voting_threshold',
            field=models.CharField(
                choices=[('admins', 'Admins only'), ('25', '25% of members'), ('50', '50% of members'), ('100', '100% of members')],
                default='admins', max_length=10,
            ),
        ),
        migrations.AddField(
            model_name='contribution',
            name='has_welfare_fund',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='contribution',
            name='has_shares_fund',
            field=models.BooleanField(default=False),
        ),

        # ── WelfareFund: change community OneToOneField → nullable ForeignKey ─
        migrations.AlterField(
            model_name='welfarefund',
            name='community',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='welfare_funds',
                to='communities.community',
            ),
        ),
        migrations.AddField(
            model_name='welfarefund',
            name='contribution',
            field=models.OneToOneField(
                blank=True, null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='welfare_fund',
                to='contributions.contribution',
            ),
        ),

        # ── SharesFund ────────────────────────────────────────────────────────
        migrations.CreateModel(
            name='SharesFund',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(default='Shares Fund', max_length=255)),
                ('share_price', models.DecimalField(decimal_places=2, default=Decimal('100.00'), max_digits=12)),
                ('total_pool', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('contribution', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='shares_fund',
                    to='contributions.contribution',
                )),
            ],
        ),

        # ── ShareHolding ──────────────────────────────────────────────────────
        migrations.CreateModel(
            name='ShareHolding',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('shares_count', models.DecimalField(decimal_places=4, default=0, max_digits=16)),
                ('total_contributed', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('shares_fund', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='holdings',
                    to='contributions.sharesfund',
                )),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'unique_together': {('shares_fund', 'user')}},
        ),
    ]
