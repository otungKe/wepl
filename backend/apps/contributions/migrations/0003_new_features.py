import django.db.models.deletion
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('communities', '0002_initial'),
        ('contributions', '0002_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ---------------------------------------------------------------
        # Extend Contribution model with new fields
        # ---------------------------------------------------------------
        migrations.AddField(
            model_name='contribution',
            name='contribution_type',
            field=models.CharField(
                choices=[
                    ('POOL', 'Pool'),
                    ('ROSCA', 'ROSCA'),
                    ('VARIABLE', 'Variable'),
                    ('WELFARE', 'Welfare'),
                ],
                default='POOL',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='contribution',
            name='cycle_amount',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name='contribution',
            name='min_approvals',
            field=models.PositiveIntegerField(default=2),
        ),
        # ---------------------------------------------------------------
        # Add note field to ContributionTransaction
        # ---------------------------------------------------------------
        migrations.AddField(
            model_name='contributiontransaction',
            name='note',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        # ---------------------------------------------------------------
        # Add ADVANCE and REPAYMENT transaction types
        # ---------------------------------------------------------------
        migrations.AlterField(
            model_name='contributiontransaction',
            name='transaction_type',
            field=models.CharField(
                choices=[
                    ('CONTRIBUTION', 'Contribution'),
                    ('WITHDRAWAL', 'Withdrawal'),
                    ('ADVANCE', 'Advance'),
                    ('REPAYMENT', 'Repayment'),
                ],
                max_length=20,
            ),
        ),

        # ---------------------------------------------------------------
        # ROSCASlot
        # ---------------------------------------------------------------
        migrations.CreateModel(
            name='ROSCASlot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('slot_order', models.PositiveIntegerField()),
                ('cycle_number', models.PositiveIntegerField(default=1)),
                ('has_received', models.BooleanField(default=False)),
                ('received_at', models.DateTimeField(blank=True, null=True)),
                ('payout_amount', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('contribution', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='rosca_slots',
                    to='contributions.contribution',
                )),
                ('participant', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='rosca_slots',
                    to='contributions.contributionparticipant',
                )),
            ],
            options={'ordering': ['cycle_number', 'slot_order']},
        ),
        migrations.AlterUniqueTogether(
            name='roscaslot',
            unique_together={('contribution', 'slot_order', 'cycle_number')},
        ),

        # ---------------------------------------------------------------
        # DisbursementRequest
        # ---------------------------------------------------------------
        migrations.CreateModel(
            name='DisbursementRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('reason', models.TextField()),
                ('recipient_phone', models.CharField(max_length=20)),
                ('status', models.CharField(
                    choices=[
                        ('PENDING', 'Pending'),
                        ('APPROVED', 'Approved'),
                        ('REJECTED', 'Rejected'),
                        ('EXECUTED', 'Executed'),
                    ],
                    default='PENDING',
                    max_length=20,
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('executed_at', models.DateTimeField(blank=True, null=True)),
                ('contribution', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='disbursement_requests',
                    to='contributions.contribution',
                )),
                ('requested_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='disbursement_requests',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
        ),

        # ---------------------------------------------------------------
        # DisbursementVote
        # ---------------------------------------------------------------
        migrations.CreateModel(
            name='DisbursementVote',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('vote', models.CharField(
                    choices=[('APPROVE', 'Approve'), ('REJECT', 'Reject')],
                    max_length=10,
                )),
                ('voted_at', models.DateTimeField(auto_now_add=True)),
                ('request', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='votes',
                    to='contributions.disbursementrequest',
                )),
                ('voter', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='disbursement_votes',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
        ),
        migrations.AlterUniqueTogether(
            name='disbursementvote',
            unique_together={('request', 'voter')},
        ),

        # ---------------------------------------------------------------
        # WelfareFund
        # ---------------------------------------------------------------
        migrations.CreateModel(
            name='WelfareFund',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(default='Welfare Fund', max_length=255)),
                ('balance', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('monthly_contribution', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('community', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='welfare_fund',
                    to='communities.community',
                )),
            ],
        ),

        # ---------------------------------------------------------------
        # WelfareContribution
        # ---------------------------------------------------------------
        migrations.CreateModel(
            name='WelfareContribution',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('fund', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='contributions',
                    to='contributions.welfarefund',
                )),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
        ),

        # ---------------------------------------------------------------
        # WelfareClaim
        # ---------------------------------------------------------------
        migrations.CreateModel(
            name='WelfareClaim',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount_requested', models.DecimalField(decimal_places=2, max_digits=12)),
                ('reason', models.TextField()),
                ('status', models.CharField(
                    choices=[
                        ('PENDING', 'Pending'),
                        ('APPROVED', 'Approved'),
                        ('REJECTED', 'Rejected'),
                        ('DISBURSED', 'Disbursed'),
                    ],
                    default='PENDING',
                    max_length=20,
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('disbursed_at', models.DateTimeField(blank=True, null=True)),
                ('claimant', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='welfare_claims',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('fund', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='claims',
                    to='contributions.welfarefund',
                )),
            ],
        ),

        # ---------------------------------------------------------------
        # WelfareVote
        # ---------------------------------------------------------------
        migrations.CreateModel(
            name='WelfareVote',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('vote', models.CharField(
                    choices=[('APPROVE', 'Approve'), ('REJECT', 'Reject')],
                    max_length=10,
                )),
                ('voted_at', models.DateTimeField(auto_now_add=True)),
                ('claim', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='votes',
                    to='contributions.welfareclaim',
                )),
                ('voter', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='welfare_votes',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
        ),
        migrations.AlterUniqueTogether(
            name='welfarevote',
            unique_together={('claim', 'voter')},
        ),

        # ---------------------------------------------------------------
        # EmergencyAdvance
        # ---------------------------------------------------------------
        migrations.CreateModel(
            name='EmergencyAdvance',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('interest_rate', models.DecimalField(decimal_places=2, default=Decimal('10.00'), max_digits=5)),
                ('status', models.CharField(
                    choices=[
                        ('PENDING', 'Pending'),
                        ('APPROVED', 'Approved'),
                        ('REJECTED', 'Rejected'),
                        ('DISBURSED', 'Disbursed'),
                        ('REPAID', 'Repaid'),
                    ],
                    default='PENDING',
                    max_length=20,
                )),
                ('amount_repaid', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('repayment_due', models.DateField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('borrower', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='advances',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('contribution', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='advances',
                    to='contributions.contribution',
                )),
            ],
        ),
    ]
