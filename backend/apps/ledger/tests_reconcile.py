"""Tests for ledger reconciliation & integrity (P0-08)."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ledger import coa, posting_map as pm
from apps.ledger.balances import account_balance, reconcile_account
from apps.ledger.models import AccountBalance
from apps.ledger.money import Money
from apps.ledger.posting import post_journal
from apps.ledger.tasks import reconcile_ledger

User = get_user_model()


class ReconcileLedgerTests(TestCase):

    def setUp(self):
        coa.seed_chart_of_accounts()
        self.alice = User.objects.create(phone_number="+254700000950")
        post_journal(
            idempotency_key="rc1", op_type=pm.Op.CONTRIBUTION,
            lines=pm.contribution_lines(
                member=self.alice, fund_type="contribution", fund_id=1, gross=Money("1000")),
        )

    def test_clean_ledger_reports_balanced_no_drift(self):
        report = reconcile_ledger()
        self.assertTrue(report['balanced'])
        self.assertEqual(report['drift_count'], 0)

    def test_detects_and_repairs_projection_drift(self):
        member = coa.member_fund_account(
            user=self.alice, fund_type="contribution", fund_id=1)
        # Corrupt the projection directly (simulating drift), bypassing post_journal.
        AccountBalance.objects.filter(account=member).update(credit_total=Decimal("999.0000"))
        self.assertFalse(reconcile_account(member)['ok'])

        report = reconcile_ledger(repair=True)

        self.assertGreaterEqual(report['drift_count'], 1)
        # Projection repaired back to the replay of immutable lines.
        self.assertTrue(reconcile_account(member)['ok'])
        self.assertEqual(account_balance(member), Decimal("1000.0000"))
        # The trial balance (from lines, not the projection) was never affected.
        self.assertTrue(report['balanced'])

    def test_no_repair_flag_reports_without_fixing(self):
        member = coa.member_fund_account(
            user=self.alice, fund_type="contribution", fund_id=1)
        AccountBalance.objects.filter(account=member).update(credit_total=Decimal("1.0000"))

        report = reconcile_ledger(repair=False)

        self.assertGreaterEqual(report['drift_count'], 1)
        self.assertFalse(report['repaired'])
        # Still drifted — nothing was repaired.
        self.assertFalse(reconcile_account(member)['ok'])
