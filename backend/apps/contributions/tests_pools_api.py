"""API tests for the collective-fund admin actions (ADR-0027).

Thin endpoints over the governed services — verify wiring, request validation,
the admin gate over the wire, and the end-to-end ledger effect.
"""
from decimal import Decimal

from django.test import TestCase

from apps.communities.services import CommunityService
from apps.contributions.services import ContributionService
from apps.contributions.tests_policy import active_client, make_user
from apps.ledger import coa, posting_map as pm
from apps.ledger.balances import account_balance, economic_interest
from apps.ledger.money import Money
from apps.ledger.posting import post_journal


class PoolFundApiTests(TestCase):
    def setUp(self):
        coa.seed_chart_of_accounts()
        self.admin = make_user("254700000980")            # community + contribution creator (admin)
        CommunityService.create_community(self.admin, {"name": "Ops Chama"})
        self.contribution = ContributionService.create_contribution(self.admin, {"title": "Fund"})
        self.cid = self.contribution.id
        self.alice = make_user("254700000981")
        self.bob = make_user("254700000982")
        self._fund(self.alice, "6000", "pa-a")
        self._fund(self.bob, "4000", "pa-b")

    def _fund(self, member, amount, key):
        post_journal(idempotency_key=key, op_type=pm.Op.CONTRIBUTION,
                     lines=pm.contribution_lines(member=member, fund_type="contribution",
                                                 fund_id=self.cid, gross=Money(amount)))

    def _interest(self, member):
        return economic_interest(member, "contribution", self.cid)

    def test_admin_can_record_pool_expense(self):
        r = active_client(self.admin).post(
            f"/api/contributions/{self.cid}/pool-expense/",
            {"amount": "1000", "apportion": "pro_rata", "reason": "Venue"}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self._interest(self.alice), Decimal("5400.0000"))
        self.assertEqual(self._interest(self.bob), Decimal("3600.0000"))

    def test_admin_can_record_income_then_distribute(self):
        c = active_client(self.admin)
        r1 = c.post(f"/api/contributions/{self.cid}/external-income/",
                    {"amount": "30000", "source": "Business"}, format="json")
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(account_balance(coa.retained_surplus_account(fund_id=self.cid)),
                         Decimal("30000.0000"))
        r2 = c.post(f"/api/contributions/{self.cid}/distribute/",
                    {"amount": "30000", "apportion": "pro_rata"}, format="json")
        self.assertEqual(r2.status_code, 201)
        self.assertEqual(self._interest(self.alice), Decimal("24000.0000"))
        self.assertEqual(self._interest(self.bob), Decimal("16000.0000"))

    def test_non_admin_is_forbidden(self):
        r = active_client(self.alice).post(
            f"/api/contributions/{self.cid}/pool-expense/", {"amount": "100"}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_bad_amount_is_rejected(self):
        r = active_client(self.admin).post(
            f"/api/contributions/{self.cid}/external-income/", {"amount": "0"}, format="json")
        self.assertEqual(r.status_code, 400)
