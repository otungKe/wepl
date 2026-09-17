"""External income → retained surplus → declared distribution (ADR-0027).

Business/external proceeds land collectively as a pool's retained surplus with no
member position change; a declared distribution then crystallises that collective
equity into redeemable member positions, apportioned by the sharing rule. Two
stages, both governed; the ledger stays balanced throughout.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from apps.communities.services import CommunityService
from apps.contributions.services import ContributionService
from apps.ledger import coa, posting_map as pm
from apps.ledger.balances import account_balance, economic_interest, fund_balance, trial_balance
from apps.ledger.money import Money
from apps.ledger.posting import post_journal

User = get_user_model()


class ExternalIncomeTests(TestCase):
    def setUp(self):
        coa.seed_chart_of_accounts()
        self.admin = User.objects.create(phone_number="+254700000970")
        CommunityService.create_community(self.admin, {"name": "Biz Chama"})
        self.contribution = ContributionService.create_contribution(self.admin, {"title": "Venture"})
        self.cid = self.contribution.id
        self.alice = User.objects.create(phone_number="+254700000971")
        self.bob = User.objects.create(phone_number="+254700000972")
        self._fund(self.alice, "6000", "fi-a")
        self._fund(self.bob, "4000", "fi-b")
        self.float = coa.mpesa_float_account()

    def _fund(self, member, amount, key):
        post_journal(idempotency_key=key, op_type=pm.Op.CONTRIBUTION,
                     lines=pm.contribution_lines(member=member, fund_type="contribution",
                                                 fund_id=self.cid, gross=Money(amount)))

    def _interest(self, member):
        return economic_interest(member, "contribution", self.cid)

    def _surplus(self):
        return account_balance(coa.retained_surplus_account(fund_id=self.cid))

    def test_external_income_lands_collectively_not_on_members(self):
        ContributionService.record_external_income(self.admin, self.cid, Decimal("90000"),
                                                   source="Q1 business proceeds")
        # Members' positions are untouched; the money is the group's retained surplus.
        self.assertEqual(self._interest(self.alice), Decimal("6000.0000"))
        self.assertEqual(self._interest(self.bob), Decimal("4000.0000"))
        self.assertEqual(self._surplus(), Decimal("90000.0000"))
        self.assertEqual(account_balance(self.float), Decimal("100000.0000"))  # 10k + 90k
        # Retained surplus is NOT part of the members' contribution pool.
        self.assertEqual(fund_balance("contribution", self.cid), Decimal("10000"))
        self.assertTrue(trial_balance()["balanced"])

    def test_declared_distribution_crystallises_to_members_pro_rata(self):
        ContributionService.record_external_income(self.admin, self.cid, Decimal("30000"))
        ContributionService.declare_distribution(self.admin, self.cid, Decimal("30000"),
                                                 apportion="pro_rata", reason="FY dividend")
        # 6000:4000 → 18000 / 12000 crystallised into redeemable positions.
        self.assertEqual(self._interest(self.alice), Decimal("24000.0000"))
        self.assertEqual(self._interest(self.bob), Decimal("16000.0000"))
        self.assertEqual(self._surplus(), Decimal("0.0000"))
        self.assertTrue(trial_balance()["balanced"])

    def test_distribution_cannot_exceed_retained_surplus(self):
        ContributionService.record_external_income(self.admin, self.cid, Decimal("1000"))
        with self.assertRaises(ValidationError):
            ContributionService.declare_distribution(self.admin, self.cid, Decimal("1001"))

    def test_external_income_and_distribution_are_admin_only(self):
        with self.assertRaises(PermissionDenied):
            ContributionService.record_external_income(self.alice, self.cid, Decimal("100"))
        with self.assertRaises(PermissionDenied):
            ContributionService.declare_distribution(self.alice, self.cid, Decimal("100"))
