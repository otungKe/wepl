"""Phase 4 reporting tests — reports reconcile to the ledger and are
point-in-time reproducible from immutable lines."""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.ledger.coa import seed_chart_of_accounts
from apps.ledger.models import Account, JournalLine
from apps.ledger.posting import Line, post_journal
from apps.ledger import reporting


class ReportingTests(TestCase):
    def setUp(self):
        seed_chart_of_accounts()
        self.asset = Account.objects.filter(type=Account.Type.ASSET).first()
        self.liab = Account.objects.filter(type=Account.Type.LIABILITY).first()
        self.income = Account.objects.filter(type=Account.Type.INCOME).first()
        self.t1 = timezone.now() - timedelta(days=2)
        self.t2 = timezone.now()

        # J1: a contribution — asset up, liability up.
        post_journal(
            idempotency_key='rep-j1', op_type='CONTRIBUTION', posted_at=self.t1,
            lines=[
                Line(account=self.asset, direction=JournalLine.Direction.DEBIT, amount=Decimal('1000')),
                Line(account=self.liab, direction=JournalLine.Direction.CREDIT, amount=Decimal('1000')),
            ],
        )
        # J2: a fee — asset up, income up.
        post_journal(
            idempotency_key='rep-j2', op_type='CONTRIBUTION', posted_at=self.t2,
            lines=[
                Line(account=self.asset, direction=JournalLine.Direction.DEBIT, amount=Decimal('100')),
                Line(account=self.income, direction=JournalLine.Direction.CREDIT, amount=Decimal('100')),
            ],
        )

    def test_trial_balance_is_balanced(self):
        tb = reporting.trial_balance()
        self.assertEqual(tb['total_debit'], Decimal('1100'))
        self.assertEqual(tb['total_credit'], Decimal('1100'))
        self.assertTrue(tb['balanced'])

    def test_trial_balance_point_in_time(self):
        tb = reporting.trial_balance(as_of=self.t1)
        self.assertEqual(tb['total_debit'], Decimal('1000'))  # J2 excluded
        self.assertTrue(tb['balanced'])

    def test_balance_sheet_equation_holds(self):
        bs = reporting.balance_sheet()
        self.assertEqual(bs['assets'], Decimal('1100'))
        self.assertEqual(bs['liabilities'], Decimal('1000'))
        self.assertEqual(bs['retained_earnings'], Decimal('100'))  # income - expense
        self.assertTrue(bs['balanced'])  # assets == liab + equity + retained

    def test_income_statement_net(self):
        inc = reporting.income_statement()
        self.assertEqual(inc['income_total'], Decimal('100'))
        self.assertEqual(inc['net_income'], Decimal('100'))

    def test_statement_of_account_running_balance(self):
        st = reporting.statement_of_account(self.asset)
        self.assertEqual(st['opening_balance'], Decimal('0'))
        self.assertEqual(st['closing_balance'], Decimal('1100'))
        self.assertEqual(len(st['entries']), 2)
        self.assertEqual(st['entries'][-1]['balance'], Decimal('1100'))

    def test_statement_opening_from_prior_period(self):
        st = reporting.statement_of_account(self.asset, start=self.t2 - timedelta(hours=1))
        self.assertEqual(st['opening_balance'], Decimal('1000'))  # J1 is the opening
        self.assertEqual(st['closing_balance'], Decimal('1100'))

    def test_export_rows(self):
        rows = list(reporting.export_journal_rows())
        self.assertEqual(len(rows), 4)  # 2 journals × 2 lines
        self.assertEqual(set(rows[0].keys()), set(reporting.EXPORT_COLUMNS))


class ReportingApiTests(TestCase):
    def setUp(self):
        from rest_framework.test import APIClient
        from django.contrib.auth import get_user_model
        seed_chart_of_accounts()
        self.User = get_user_model()
        self.staff = self.User.objects.create_user(phone_number='254700000010')
        self.staff.is_staff = True
        self.staff.save()
        self.client = APIClient()
        self.client.force_authenticate(user=self.staff)

    def test_trial_balance_endpoint(self):
        r = self.client.get('/api/ledger/reports/trial-balance/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('balanced', r.json())

    def test_non_staff_forbidden(self):
        from rest_framework.test import APIClient
        u = self.User.objects.create_user(phone_number='254700000011')
        client = APIClient()
        client.force_authenticate(user=u)
        r = client.get('/api/ledger/reports/trial-balance/')
        self.assertEqual(r.status_code, 403)
