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

    def test_reverse_financial_transaction_restores_and_is_idempotent(self):
        from apps.ledger.writer import create_fin_transaction
        from apps.ledger.posting import reverse_financial_transaction

        ft, _ = create_fin_transaction(
            idempotency_key="ft-rev", op_type=pm.Op.DISBURSEMENT,
            amount=Decimal("500"), initiated_by=self.bob)
        post_journal(
            idempotency_key="je-ft-rev", op_type=pm.Op.DISBURSEMENT,
            lines=pm.disbursement_lines(
                member=self.bob, fund_type="contribution", fund_id=5, amount=Money("500")),
            financial_transaction=ft)
        member = coa.member_fund_account(user=self.bob, fund_type="contribution", fund_id=5)
        self.assertEqual(account_balance(member), Decimal("-500.0000"))

        rev = reverse_financial_transaction(ft, note="payout failed")
        self.assertIsNotNone(rev)
        self.assertEqual(account_balance(member), Decimal("0.0000"))
        self.assertEqual(account_balance(self.float), Decimal("0.0000"))
        # idempotent: a second call returns the same reversal, posts nothing new
        again = reverse_financial_transaction(ft, note="payout failed")
        self.assertEqual(again.id, rev.id)
        self.assertTrue(trial_balance()["balanced"])

    def test_fund_balance_sums_member_subledgers(self):
        from apps.ledger.balances import fund_balance
        self._post("fb1", pm.Op.CONTRIBUTION, pm.contribution_lines(
            member=self.alice, fund_type="contribution", fund_id=88, gross=Money("1000")))
        self._post("fb2", pm.Op.CONTRIBUTION, pm.contribution_lines(
            member=self.bob, fund_type="contribution", fund_id=88, gross=Money("500")))
        self.assertEqual(fund_balance("contribution", 88), Decimal("1500.0000"))
        self._post("fb3", pm.Op.DISBURSEMENT, pm.disbursement_lines(
            member=self.alice, fund_type="contribution", fund_id=88, amount=Money("300")))
        self.assertEqual(fund_balance("contribution", 88), Decimal("1200.0000"))

    def test_advance_repayment_interest_only(self):
        # principal already cleared elsewhere → a pure-interest payment is valid
        self._post("ar-int", pm.Op.ADVANCE_REPAYMENT, pm.advance_repayment_lines(
            member=self.bob, advance_id=99, principal=Money("0"), interest=Money("50")))
        self.assertEqual(account_balance(coa.interest_income_account()), Decimal("50.0000"))
        self.assertEqual(account_balance(self.float), Decimal("50.0000"))
        self.assertTrue(trial_balance()["balanced"])

    def test_advance_repayment_principal_only(self):
        self._post("ar-disb", pm.Op.ADVANCE_DISBURSEMENT, pm.advance_disbursement_lines(
            member=self.bob, advance_id=99, principal=Money("200")))
        self._post("ar-prin", pm.Op.ADVANCE_REPAYMENT, pm.advance_repayment_lines(
            member=self.bob, advance_id=99, principal=Money("200"), interest=Money("0")))
        ar = coa.member_receivable_account(user=self.bob, fund_id=99)
        self.assertEqual(account_balance(ar), Decimal("0.0000"))
        self.assertEqual(account_balance(coa.interest_income_account()), Decimal("0.0000"))
        self.assertTrue(trial_balance()["balanced"])

    def test_balance_helper_variants(self):
        from apps.ledger.balances import (
            member_fund_balance, user_fund_balances, fund_member_balances, fund_balances,
        )
        self._post("b1", pm.Op.CONTRIBUTION, pm.contribution_lines(
            member=self.alice, fund_type="contribution", fund_id=77, gross=Money("1000")))
        self._post("b2", pm.Op.CONTRIBUTION, pm.contribution_lines(
            member=self.bob, fund_type="contribution", fund_id=77, gross=Money("400")))
        self._post("b3", pm.Op.CONTRIBUTION, pm.contribution_lines(
            member=self.alice, fund_type="contribution", fund_id=78, gross=Money("50")))

        # member_fund_balance — non-creating; 0 when nothing posted
        self.assertEqual(member_fund_balance(self.alice, "contribution", 77), Decimal("1000.0000"))
        self.assertEqual(member_fund_balance(self.alice, "contribution", 999), Decimal("0"))

        # user_fund_balances — one user across many funds, one query
        ub = user_fund_balances(self.alice, "contribution", [77, 78])
        self.assertEqual(ub[77], Decimal("1000.0000"))
        self.assertEqual(ub[78], Decimal("50.0000"))

        # fund_member_balances — one fund across members
        fmb = fund_member_balances("contribution", 77)
        self.assertEqual(fmb[self.alice.id], Decimal("1000.0000"))
        self.assertEqual(fmb[self.bob.id], Decimal("400.0000"))

        # fund_balances — many funds at once
        fb = fund_balances("contribution", [77, 78])
        self.assertEqual(fb[77], Decimal("1400.0000"))
        self.assertEqual(fb[78], Decimal("50.0000"))

    def test_non_positive_amounts_rejected(self):
        with self.assertRaises(ValueError):
            pm.contribution_lines(member=self.alice, fund_type="contribution",
                                  fund_id=1, gross=Money("0"))
        with self.assertRaises(ValueError):
            # fee >= gross leaves a non-positive net
            pm.contribution_lines(member=self.alice, fund_type="contribution",
                                  fund_id=1, gross=Money("10"), fee=Money("10"))
