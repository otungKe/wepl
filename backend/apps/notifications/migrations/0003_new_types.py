from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0002_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='notification',
            name='notification_type',
            field=models.CharField(
                choices=[
                    ('community_join',         'Community Join'),
                    ('conversation_created',   'Conversation Created'),
                    ('new_message',            'New Message'),
                    ('contribution_payment',   'Contribution Payment'),
                    ('payment_recorded',       'Payment Recorded'),
                    ('contribution_milestone', 'Contribution Milestone'),
                    ('contribution_joined',    'Contribution Joined'),
                    ('rosca_rotation_set',     'ROSCA Rotation Set'),
                    ('rosca_payout',           'ROSCA Payout'),
                    ('disbursement_requested', 'Disbursement Requested'),
                    ('disbursement_rejected',  'Disbursement Rejected'),
                    ('disbursement_executed',  'Disbursement Executed'),
                    ('welfare_claim',          'Welfare Claim'),
                    ('welfare_rejected',       'Welfare Rejected'),
                    ('welfare_disbursed',      'Welfare Disbursed'),
                    ('advance_requested',      'Advance Requested'),
                    ('advance_approved',       'Advance Approved'),
                    ('advance_rejected',       'Advance Rejected'),
                ],
                max_length=50,
            ),
        ),
    ]
