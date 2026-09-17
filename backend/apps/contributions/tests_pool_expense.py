"""Goal-pool collective expense — apportioned across members (ADR-0027).

A jointly-owned pool spends on a shared expense; the cost is borne by the funded
members in proportion to their position (pro-rata) or equally (per-capita). Each
member's economic interest drops by their share, cash leaves float for the total,
and the ledger stays balanced.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from apps.communities.services import CommunityService
from apps.contributions.services import ContributionService
from apps.contributions.services.contribution import _apportion_amount
from apps.ledger import coa, posting_map as pm
from apps.ledger.balances import account_balance, economic_interest, fund_balance, trial_balance
from apps.ledger.money import Money
from apps.ledger.posting import post_journal

User = get_user_model()


class ApportionHelperTests(TestCase):
    def test_pro_rata_sums_back_to_total_exactly(self):
        shares = _apportion_amount(Decimal("100"), [(1, Decimal("6000")), (2, Decimal("4000"))])
        self.assertEqual(shares, {1: Decimal("60.00"), 2: Decimal("40.00")})

    def test_rounding_remainder_is_distributed(self):
        # 100 split three equal ways → 33.34 / 33.33 / 33.33, summing to exactly 100.
        shares = _apportion_amount(Decimal("100"), [(1, Decimal("1")), (2, Decimal("1")), (3, Decimal("1"))])
        self.assertEqual(sum(shares.values()), Decimal("100.00"))
        self.assertEqual(sorted(shares.values()), [Decimal("33.33"), Decimal("33.33"), Decimal("33.34")])


class PoolExpenseTests(TestCase):
    def setUp(self):
        coa.seed_chart_of_accounts()
        self.admin = User.objects.create(phone_number="+254700000960")
        CommunityService.create_community(self.admin, {"name": "Family"})
        self.contribution = ContributionService.create_contribution(self.admin, {"title": "Reunion"})
        self.cid = self.contribution.id
        self.alice = User.objects.create(phone_number="+254700000961")
        self.bob = User.objects.create(phone_number="+254700000962")
        self._fund(self.alice, "6000", "f-a")
        self._fund(self.bob, "4000", "f-b")
        self.float = coa.mpesa_float_account()

    def _fund(self, member, amount, key):
        post_journal(idempotency_key=key, op_type=pm.Op.CONTRIBUTION,
                     lines=pm.contribution_lines(member=member, fund_type="contribution",
                                                 fund_id=self.cid, gross=Money(amount)))

    def _interest(self, member):
        return economic_interest(member, "contribution", self.cid)

    def test_pro_rata_expense_draws_positions_proportionally(self):
        ContributionService.record_pool_expense(
            self.admin, self.cid, Decimal("1000"), apportion="pro_rata", reason="Venue")
        self.assertEqual(self._interest(self.alice), Decimal("5400.0000"))   # 6000 − 600
        self.assertEqual(self._interest(self.bob), Decimal("3600.0000"))     # 4000 − 400
        self.assertEqual(fund_balance("contribution", self.cid), Decimal("9000"))
        self.assertEqual(account_balance(self.float), Decimal("9000.0000"))  # 10000 in − 1000 out
        self.assertTrue(trial_balance()["balanced"])

    def test_per_capita_expense_splits_equally(self):
        ContributionService.record_pool_expense(
            self.admin, self.cid, Decimal("1000"), apportion="per_capita")
        self.assertEqual(self._interest(self.alice), Decimal("5500.0000"))   # 6000 − 500
        self.assertEqual(self._interest(self.bob), Decimal("3500.0000"))     # 4000 − 500
        self.assertTrue(trial_balance()["balanced"])

    def test_expense_cannot_exceed_pool(self):
        with self.assertRaises(ValidationError):
            ContributionService.record_pool_expense(self.admin, self.cid, Decimal("10001"))

    def test_only_admin_can_spend_pool(self):
        with self.assertRaises(PermissionDenied):
            ContributionService.record_pool_expense(self.alice, self.cid, Decimal("100"))
