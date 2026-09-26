"""Welfare premiums fund the pool and claims are paid from it (ADR-0027 §0.2).

A premium buys cover, not a share: it goes into the welfare fund itself and no
member holds a refundable welfare balance. A claim is paid from the fund, so the
claimant owes the fund nothing afterwards.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.communities.models import CommunityMembership
from apps.communities.services import CommunityService
from apps.contributions.services import WelfareService
from apps.ledger import coa
from apps.ledger.balances import (
    account_balance, fund_balance, member_fund_balance, trial_balance,
)
from apps.ledger.models import Account

User = get_user_model()


def _verified(phone):
    from apps.verification.models import KYCProfile
    user = User.objects.create(phone_number=phone, is_phone_verified=True)
    KYCProfile.objects.create(
        user=user, status="approved", given_names="Test", surname="User",
        id_number=f"ID{user.pk}", date_of_birth=date(1990, 1, 1),
    )
    return user


class WelfarePoolTests(TestCase):
    def setUp(self):
        coa.seed_chart_of_accounts()
        self.admin = _verified("+254700000980")
        self.alice = _verified("+254700000981")
        self.bob = _verified("+254700000982")
        community = CommunityService.create_community(
            self.admin, {"name": "Welfare Chama", "has_welfare_fund": True})
        type(community).objects.filter(pk=community.pk).update(cooling_off_days=0)
        community.refresh_from_db()
        for user in (self.alice, self.bob):
            CommunityService.join_community(user, community)
        CommunityMembership.objects.filter(community=community, user=self.admin).update(role="admin")
        self.fund = WelfareService.get_or_create_community_fund(community)
        WelfareService.contribute_to_welfare(self.fund.id, self.alice, Decimal("500"), "R-A")
        WelfareService.contribute_to_welfare(self.fund.id, self.bob, Decimal("300"), "R-B")

    def _pool(self):
        return account_balance(coa.pool_account(fund_type="welfare", fund_id=self.fund.id))

    def test_premiums_go_into_the_pool_not_to_members(self):
        self.assertEqual(self._pool(), Decimal("800"))
        self.assertEqual(fund_balance("welfare", self.fund.id), Decimal("800"))
        self.assertEqual(member_fund_balance(self.alice, "welfare", self.fund.id), Decimal("0"))
        self.assertFalse(Account.objects.filter(
            fund_type="welfare", fund_id=self.fund.id, owner__isnull=False).exists())
        self.assertTrue(trial_balance()["balanced"])

    def test_claim_is_paid_from_the_fund_not_charged_to_the_claimant(self):
        claim = WelfareService.submit_claim(self.fund.id, self.bob, Decimal("600"), "Hospital")
        WelfareService.approve_claim(claim.id, self.admin)
        self.assertEqual(self._pool(), Decimal("200"))
        # Bob paid 300 and was paid 600: under the old recipe he showed −300.
        self.assertEqual(member_fund_balance(self.bob, "welfare", self.fund.id), Decimal("0"))
        self.assertEqual(account_balance(coa.mpesa_float_account()), Decimal("200"))
        self.assertTrue(trial_balance()["balanced"])

    def test_premium_is_idempotent_on_the_receipt(self):
        WelfareService.contribute_to_welfare(self.fund.id, self.alice, Decimal("500"), "R-A")
        self.assertEqual(self._pool(), Decimal("800"))
