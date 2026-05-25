from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('contributions', '0013_standingorder_schedule'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='FinancialTransaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('op_type', models.CharField(choices=[
                    ('CONTRIBUTION',         'Member Contribution'),
                    ('DISBURSEMENT',         'Disbursement'),
                    ('STANDING_ORDER',       'Standing Order Payout'),
                    ('ROSCA_PAYOUT',         'ROSCA Payout'),
                    ('ADVANCE_DISBURSEMENT', 'Emergency Advance Disbursement'),
                    ('ADVANCE_REPAYMENT',    'Emergency Advance Repayment'),
                    ('WELFARE_CONTRIBUTION', 'Welfare Contribution'),
                    ('WELFARE_CLAIM',        'Welfare Claim Disbursement'),
                    ('SHARES_PURCHASE',      'Shares Purchase'),
                ], max_length=30)),
                ('state', models.CharField(choices=[
                    ('PENDING',    'Pending'),
                    ('PROCESSING', 'Processing'),
                    ('SUCCESS',    'Success'),
                    ('FAILED',     'Failed'),
                    ('REVERSED',   'Reversed'),
                ], default='PENDING', max_length=20)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=14)),
                ('idempotency_key', models.CharField(db_index=True, max_length=128, unique=True)),
                ('context_type', models.CharField(blank=True, max_length=30)),
                ('context_id', models.PositiveIntegerField(blank=True, null=True)),
                ('recipient_phone', models.CharField(blank=True, max_length=20)),
                ('mpesa_checkout_id',     models.CharField(blank=True, max_length=255, null=True, unique=True)),
                ('mpesa_conversation_id', models.CharField(blank=True, max_length=255, null=True, unique=True)),
                ('mpesa_receipt',         models.CharField(blank=True, max_length=50,  null=True, unique=True)),
                ('note',           models.TextField(blank=True)),
                ('failure_reason', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('initiated_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='initiated_fin_txs',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('contribution', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='fin_transactions',
                    to='contributions.contribution',
                )),
                ('welfare_fund', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='fin_transactions',
                    to='contributions.welfarefund',
                )),
                ('shares_fund', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='fin_transactions',
                    to='contributions.sharesfund',
                )),
            ],
            options={'indexes': [
                models.Index(fields=['state', 'op_type'],   name='ledger_ft_state_op_idx'),
                models.Index(fields=['state', 'updated_at'], name='ledger_ft_state_updated_idx'),
                models.Index(fields=['context_type', 'context_id'], name='ledger_ft_context_idx'),
            ]},
        ),
        migrations.CreateModel(
            name='LedgerEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=14)),
                ('direction', models.CharField(choices=[('CREDIT', 'Credit'), ('DEBIT', 'Debit')], max_length=6)),
                ('entry_type', models.CharField(choices=[
                    ('MEMBER_CONTRIBUTION',  'Member Contribution'),
                    ('ADVANCE_REPAYMENT',    'Advance Repayment'),
                    ('WELFARE_CONTRIBUTION', 'Welfare Contribution'),
                    ('SHARES_PURCHASE',      'Shares Purchase'),
                    ('REVERSAL_CREDIT',      'Reversal Credit'),
                    ('DISBURSEMENT',         'Disbursement'),
                    ('STANDING_ORDER',       'Standing Order Payout'),
                    ('ROSCA_PAYOUT',         'ROSCA Payout'),
                    ('ADVANCE_DISBURSEMENT', 'Emergency Advance Disbursement'),
                    ('WELFARE_CLAIM',        'Welfare Claim Disbursement'),
                    ('REVERSAL_DEBIT',       'Reversal Debit'),
                ], max_length=30)),
                ('idempotency_key', models.CharField(db_index=True, max_length=128, unique=True)),
                ('mpesa_receipt', models.CharField(blank=True, db_index=True, max_length=50, null=True)),
                ('note', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='ledger_entries',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('financial_transaction', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='ledger_entries',
                    to='ledger.financialtransaction',
                )),
                ('contribution', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='ledger_entries',
                    to='contributions.contribution',
                )),
                ('welfare_fund', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='ledger_entries',
                    to='contributions.welfarefund',
                )),
                ('shares_fund', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='ledger_entries',
                    to='contributions.sharesfund',
                )),
            ],
            options={'indexes': [
                models.Index(fields=['contribution', 'direction', 'created_at'], name='ledger_le_contrib_dir_idx'),
                models.Index(fields=['welfare_fund',  'direction', 'created_at'], name='ledger_le_welfare_dir_idx'),
                models.Index(fields=['shares_fund',   'direction', 'created_at'], name='ledger_le_shares_dir_idx'),
                models.Index(fields=['user',           'created_at'],             name='ledger_le_user_idx'),
            ]},
        ),
    ]
