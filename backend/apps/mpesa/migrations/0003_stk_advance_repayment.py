import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Add advance_repayment payment type and advance FK to MpesaSTKRequest.

    Needed so STK Push can target a specific EmergencyAdvance and the
    process_stk_payment Celery task can call EmergencyAdvanceService.repay()
    with the correct advance_id after the callback confirms payment.
    """

    dependencies = [
        ('mpesa', '0002_stk_payment_type'),
        ('contributions', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='mpesastkrequest',
            name='advance',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='stk_requests',
                to='contributions.emergencyadvance',
            ),
        ),
        migrations.AlterField(
            model_name='mpesastkrequest',
            name='payment_type',
            field=models.CharField(
                choices=[
                    ('contribution',      'Contribution'),
                    ('welfare',           'Welfare Fund'),
                    ('shares',            'Shares Fund'),
                    ('advance_repayment', 'Advance Repayment'),
                ],
                default='contribution',
                max_length=20,
            ),
        ),
    ]
