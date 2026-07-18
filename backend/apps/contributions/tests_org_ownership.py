"""Organization-owned ledger positions + ownership reallocation (ADR-0027).

The ownership axis is individual / collective / organization. These cover the
organization case: an org can hold a fund sub-ledger position, and a member's
position can be *reallocated* to an org (a governed ownership change that moves
no cash and conserves the pool).
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

from apps.communities.services import CommunityService
from apps.contributions.services import ContributionService
from apps.ledger import coa, posting_map as pm
from apps.ledger.balances import (
    fund_balance, member_fund_balance, org_fund_balance, trial_balance,
)
from apps.ledger.models import Account
from apps.ledger.money import Money
from apps.ledger.posting import post_journal

User = get_user_model()


class OrgOwnershipTests(TestCase):
    def setUp(self):
        coa.seed_chart_of_accounts()
        self.alice = User.objects.create(phone_number="+254700000990")
        self.community = CommunityService.create_community(self.alice, {"name": "Co-op"})
        self.contribution = ContributionService.create_contribution(
            self.alice, {"title": "Venture", "community": self.community})
        self.cid = self.contribution.id
        # The community's Organization is the legal entity (ADR-0026 spine).
        self.org = self.community.organization

    def _fund(self, member, amount, key):
        post_journal(idempotency_key=key, op_type=pm.Op.CONTRIBUTION,
                     lines=pm.contribution_lines(member=member, fund_type="contribution",
                                                 fund_id=self.cid, gross=Money(amount)))

    def test_org_can_hold_a_fund_position(self):
        acct = coa.org_fund_account(org=self.org, fund_type="contribution", fund_id=self.cid)
        self.assertIsNone(acct.owner_id)
        self.assertEqual(acct.owner_org_id, self.org.id)
        self.assertEqual(acct.type, Account.Type.LIABILITY)
        self.assertIn("-O", acct.code)   # org namespace marker

    def test_reallocate_member_position_to_org_conserves_the_pool(self):
        self._fund(self.alice, "1000", "org-f1")
        post_journal(
            idempotency_key="org-realloc-1", op_type="REALLOCATION",
            lines=pm.reallocate_to_org_lines(
                member=self.alice, org=self.org, fund_type="contribution",
                fund_id=self.cid, amount=Money("400")))

        self.assertEqual(member_fund_balance(self.alice, "contribution", self.cid), Decimal("600.0000"))
        self.assertEqual(org_fund_balance(self.org, "contribution", self.cid), Decimal("400.0000"))
        # The claim moved owners; the pool total is unchanged.
        self.assertEqual(fund_balance("contribution", self.cid), Decimal("1000"))
        self.assertTrue(trial_balance()["balanced"])

    def test_org_fund_balance_is_read_only(self):
        # No account exists yet → zero, and nothing is minted on the read.
        self.assertEqual(org_fund_balance(self.org, "contribution", self.cid), Decimal("0"))
        self.assertFalse(Account.objects.filter(
            owner_org=self.org, fund_type="contribution", fund_id=self.cid).exists())

    def test_an_account_cannot_have_two_owners(self):
        pool = coa.pool_account(fund_type="contribution", fund_id=self.cid)
        with self.assertRaises(IntegrityError):
            Account.objects.create(
                code="BAD-DUAL-OWNER", name="bad", type=Account.Type.LIABILITY,
                owner=self.alice, owner_org=self.org,
                fund_type="contribution", fund_id=self.cid, parent=pool)
