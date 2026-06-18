from decimal import Decimal

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('ledger', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Account',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(help_text='Stable Chart-of-Accounts code; account resolution keys on this.', max_length=64, unique=True)),
                ('name', models.CharField(max_length=255)),
                ('type', models.CharField(choices=[('ASSET', 'Asset'), ('LIABILITY', 'Liability'), ('EQUITY', 'Equity'), ('INCOME', 'Income'), ('EXPENSE', 'Expense')], max_length=10)),
                ('fund_type', models.CharField(blank=True, max_length=30)),
                ('fund_id', models.PositiveIntegerField(blank=True, null=True)),
                ('currency', models.CharField(default='KES', max_length=3)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('owner', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='ledger_accounts', to=settings.AUTH_USER_MODEL)),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='children', to='ledger.account')),
            ],
        ),
        migrations.CreateModel(
            name='JournalEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('idempotency_key', models.CharField(db_index=True, max_length=128, unique=True)),
                ('op_type', models.CharField(help_text='Business operation, e.g. CONTRIBUTION, DISBURSEMENT, FEE, ADJUSTMENT.', max_length=40)),
                ('narration', models.TextField(blank=True)),
                ('posted_at', models.DateTimeField(default=django.utils.timezone.now, help_text='Accounting/value date — may differ from created_at.')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='posted_journals', to=settings.AUTH_USER_MODEL)),
                ('financial_transaction', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='journals', to='ledger.financialtransaction')),
                ('reverses', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='reversed_by', to='ledger.journalentry')),
            ],
            options={
                'verbose_name_plural': 'Journal entries',
            },
        ),
        migrations.CreateModel(
            name='JournalLine',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('direction', models.CharField(choices=[('DEBIT', 'Debit'), ('CREDIT', 'Credit')], max_length=6)),
                ('amount', models.DecimalField(decimal_places=4, max_digits=20)),
                ('note', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('account', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='lines', to='ledger.account')),
                ('journal', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='lines', to='ledger.journalentry')),
            ],
        ),
        migrations.CreateModel(
            name='AccountBalance',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('debit_total', models.DecimalField(decimal_places=4, default=Decimal('0'), max_digits=20)),
                ('credit_total', models.DecimalField(decimal_places=4, default=Decimal('0'), max_digits=20)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('account', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='balance', to='ledger.account')),
            ],
        ),
        migrations.AddIndex(
            model_name='account',
            index=models.Index(fields=['type'], name='ledger_acct_type_idx'),
        ),
        migrations.AddIndex(
            model_name='account',
            index=models.Index(fields=['fund_type', 'fund_id'], name='ledger_acct_fund_idx'),
        ),
        migrations.AddIndex(
            model_name='account',
            index=models.Index(fields=['owner', 'fund_type', 'fund_id'], name='ledger_acct_owner_fund_idx'),
        ),
        migrations.AddIndex(
            model_name='journalentry',
            index=models.Index(fields=['op_type', 'posted_at'], name='ledger_je_optype_posted_idx'),
        ),
        migrations.AddConstraint(
            model_name='journalline',
            constraint=models.CheckConstraint(condition=models.Q(amount__gt=0), name='ledger_jl_amount_positive'),
        ),
        migrations.AddIndex(
            model_name='journalline',
            index=models.Index(fields=['account', 'created_at'], name='ledger_jl_account_created_idx'),
        ),
        migrations.AddIndex(
            model_name='journalline',
            index=models.Index(fields=['journal'], name='ledger_jl_journal_idx'),
        ),
    ]
