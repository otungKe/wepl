import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mpesa', '0001_initial'),
        ('contributions', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='mpesastkrequest',
            name='payment_type',
            field=models.CharField(
                choices=[
                    ('contribution', 'Contribution'),
                    ('welfare', 'Welfare Fund'),
                    ('shares', 'Shares Fund'),
                ],
                default='contribution',
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name='mpesastkrequest',
            name='contribution',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='stk_requests',
                to='contributions.contribution',
            ),
        ),
        migrations.AddField(
            model_name='mpesastkrequest',
            name='welfare_fund',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='stk_requests',
                to='contributions.welfarefund',
            ),
        ),
        migrations.AddField(
            model_name='mpesastkrequest',
            name='shares_fund',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='stk_requests',
                to='contributions.sharesfund',
            ),
        ),
    ]
