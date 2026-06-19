"""Tests for the Posting Map (P0-04).

Every recipe must (a) post a balanced journal through post_journal() and (b) move
the right accounts in the right direction. A global trial balance must remain zero
across the whole sequence.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ledger import coa, posting_map as pm
from apps.ledger.balances import account_balance, trial_balance
from apps.ledger.money import Money
from apps.ledger.posting import post_journal

User = get_user_model()


class PostingMapTests(TestCase):

    def setUp(self):
        coa.seed_chart_of_accounts()
        self.alice = User.objects.create(phone_number="+254700000900")
        self.bob = User.objects.create(phone_number="+254700000901")
        self.float = coa.mpesa_float_account()

    def _post(self, key, op, lines):
        return post_journal(idempotency_key=key, op_type=op, lines=lines)

    def test_contribution_without_fee(self):
        self._post("c1", pm.Op.CONTRIBUTION, pm.contribution_lines(
            member=self.alice, fund_type="contribution", fund_id=1, gross=Money("1000")))
        member = coa.member_fund_account(user=self.alice, fund_type="contribution", fund_id=1)
        self.assertEqual(account_balance(self.float), Decimal("1000.0000"))
        self.assertEqual(account_balance(member), Decimal("1000.0000"))  # liability owed to member
        self.assertTrue(trial_balance()["balanced"])

    def test_contribution_with_fee_splits_to_revenue(self):
        self._post("c2", pm.Op.CONTRIBUTION, pm.contribution_lines(
            member=self.alice, fund_type="contribution", fund_id=1,
            gross=Money("1000"), fee=Money("25")))
        member = coa.member_fund_account(user=self.alice, fund_type="contribution", fund_id=1)
        self.assertEqual(account_balance(self.float), Decimal("1000.0000"))
        self.assertEqual(account_balance(member), Decimal("975.0000"))
        self.assertEqual(account_balance(coa.fee_revenue_account()), Decimal("25.0000"))
        self.assertTrue(trial_balance()["balanced"])

    def test_disbursement_draws_down_member_and_float(self):
        self._post("c3", pm.Op.CONTRIBUTION, pm.contribution_lines(
            member=self.alice, fund_type="contribution", fund_id=1, gross=Money("1000")))
        self._post("d1", pm.Op.DISBURSEMENT, pm.disbursement_lines(
            member=self.alice, fund_type="contribution", fund_id=1, amount=Money("400")))
        member = coa.member_fund_account(user=self.alice, fund_type="contribution", fund_id=1)
        self.assertEqual(account_balance(self.float), Decimal("600.0000"))
        self.assertEqual(account_balance(member), Decimal("600.0000"))
        self.assertTrue(trial_balance()["balanced"])

    def test_welfare_contribution_and_claim(self):
        self._post("w1", pm.Op.WELFARE_CONTRIBUTION, pm.welfare_contribution_lines(
            member=self.alice, fund_id=7, amount=Money("500")))
        self._post("w2", pm.Op.WELFARE_CLAIM, pm.welfare_claim_lines(
            member=self.alice, fund_id=7, amount=Money("200")))
        welfare = coa.member_fund_account(user=self.alice, fund_type="welfare", fund_id=7)
        self.assertEqual(account_balance(welfare), Decimal("300.0000"))
        self.assertEqual(account_balance(self.float), Decimal("300.0000"))
        self.assertTrue(trial_balance()["balanced"])

    def test_advance_disbursement_creates_receivable(self):
        self._post("a1", pm.Op.ADVANCE_DISBURSEMENT, pm.advance_disbursement_lines(
            member=self.bob, advance_id=3, principal=Money("800")))
        ar = coa.member_receivable_account(user=self.bob, fund_id=3)
        self.assertEqual(account_balance(ar), Decimal("800.0000"))         # asset: owed to us
        self.assertEqual(account_balance(self.float), Decimal("-800.0000"))  # cash left float
        self.assertTrue(trial_balance()["balanced"])

    def test_advance_repayment_with_interest(self):
        self._post("a2", pm.Op.ADVANCE_DISBURSEMENT, pm.advance_disbursement_lines(
            member=self.bob, advance_id=3, principal=Money("800")))
        self._post("a3", pm.Op.ADVANCE_REPAYMENT, pm.advance_repayment_lines(
            member=self.bob, advance_id=3, principal=Money("800"), interest=Money("80")))
        ar = coa.member_receivable_account(user=self.bob, fund_id=3)
        self.assertEqual(account_balance(ar), Decimal("0.0000"))            # cleared
        self.assertEqual(account_balance(self.float), Decimal("80.0000"))   # net: -800 +880
        self.assertEqual(account_balance(coa.interest_income_account()), Decimal("80.0000"))
        self.assertTrue(trial_balance()["balanced"])

    def test_every_recipe_balances_and_is_idempotent(self):
        recipes = [
            ("r-con", pm.Op.CONTRIBUTION, pm.contribution_lines(
                member=self.alice, fund_type="contribution", fund_id=2,
                gross=Money("1000"), fee=Money("10"))),
            ("r-dis", pm.Op.DISBURSEMENT, pm.disbursement_lines(
                member=self.alice, fund_type="contribution", fund_id=2, amount=Money("100"))),
            ("r-wc", pm.Op.WELFARE_CONTRIBUTION, pm.welfare_contribution_lines(
                member=self.bob, fund_id=9, amount=Money("300"))),
            ("r-ad", pm.Op.ADVANCE_DISBURSEMENT, pm.advance_disbursement_lines(
                member=self.bob, advance_id=4, principal=Money("250"))),
        ]
        for key, op, lines in recipes:
            self._post(key, op, lines)
            self._post(key, op, lines)  # replay: must be a no-op, not a second posting
        # Idempotency: re-posting did not duplicate anything.
        from apps.ledger.models import JournalEntry
        self.assertEqual(JournalEntry.objects.count(), len(recipes))
        self.assertTrue(trial_balance()["balanced"])

    def test_non_positive_amounts_rejected(self):
        with self.assertRaises(ValueError):
            pm.contribution_lines(member=self.alice, fund_type="contribution",
                                  fund_id=1, gross=Money("0"))
        with self.assertRaises(ValueError):
            # fee >= gross leaves a non-positive net
            pm.contribution_lines(member=self.alice, fund_type="contribution",
                                  fund_id=1, gross=Money("10"), fee=Money("10"))
