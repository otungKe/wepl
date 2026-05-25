from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contributions', '0010_add_contribution_join_requests'),
    ]

    operations = [
        # ContributionTransaction — most common: filter by contribution, order by date
        migrations.AddIndex(
            model_name='contributiontransaction',
            index=models.Index(fields=['contribution', '-created_at'], name='contrib_tx_contrib_date_idx'),
        ),
        migrations.AddIndex(
            model_name='contributiontransaction',
            index=models.Index(fields=['user', '-created_at'], name='contrib_tx_user_date_idx'),
        ),

        # ContributionBalance — frequent lookup when rendering participant lists
        migrations.AddIndex(
            model_name='contributionbalance',
            index=models.Index(fields=['contribution', 'user'], name='contrib_balance_contrib_user_idx'),
        ),

        # ContributionParticipant — filter active participants per contribution
        migrations.AddIndex(
            model_name='contributionparticipant',
            index=models.Index(fields=['contribution', 'is_active'], name='contrib_participant_active_idx'),
        ),
        migrations.AddIndex(
            model_name='contributionparticipant',
            index=models.Index(fields=['user', 'is_active'], name='contrib_participant_user_active_idx'),
        ),

        # Contribution — discover open contributions, filter by community
        migrations.AddIndex(
            model_name='contribution',
            index=models.Index(fields=['community', 'is_active'], name='contribution_community_active_idx'),
        ),
        migrations.AddIndex(
            model_name='contribution',
            index=models.Index(fields=['visibility', 'is_active'], name='contribution_visibility_active_idx'),
        ),

        # DisbursementRequest — list by contribution, status
        migrations.AddIndex(
            model_name='disbursementrequest',
            index=models.Index(fields=['contribution', '-created_at'], name='disburse_req_contrib_date_idx'),
        ),

        # WelfareClaim — list by fund
        migrations.AddIndex(
            model_name='welfareclaim',
            index=models.Index(fields=['fund', '-created_at'], name='welfare_claim_fund_date_idx'),
        ),

        # EmergencyAdvance — list by contribution and borrower
        migrations.AddIndex(
            model_name='emergencyadvance',
            index=models.Index(fields=['contribution', '-created_at'], name='advance_contrib_date_idx'),
        ),
        migrations.AddIndex(
            model_name='emergencyadvance',
            index=models.Index(fields=['borrower', 'status'], name='advance_borrower_status_idx'),
        ),
    ]
