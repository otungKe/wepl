"""API tests for maker-checked collective-fund actions (ADR-0027).

Spending pool funds and declaring a distribution are proposed by one admin and
must be approved by a second before they post. External income (money in) stays
a direct admin action. Verifies the flow, the admin gate, and the ledger effect
over the wire.
"""
from decimal import Decimal

from django.test import TestCase

from apps.communities.models import CommunityMembership
from apps.communities.services import CommunityService
from apps.contributions.services import ContributionService
from apps.contributions.tests_policy import active_client, make_user
from apps.ledger import coa, posting_map as pm
from apps.ledger.balances import account_balance, economic_interest
from apps.ledger.money import Money
from apps.ledger.posting import post_journal


class PoolGovernanceApiTests(TestCase):
    def setUp(self):
        coa.seed_chart_of_accounts()
        self.admin = make_user("254700000980")               # creator → community admin
        self.admin2 = make_user("254700000983")              # second admin (the checker)
        self.community = CommunityService.create_community(self.admin, {"name": "Ops Chama"})
        CommunityMembership.objects.create(
            community=self.community, user=self.admin2,
            role=CommunityMembership.Role.ADMIN, is_active=True)
        self.contribution = ContributionService.create_contribution(
            self.admin, {"title": "Fund", "community": self.community})
        self.cid = self.contribution.id
        self.alice = make_user("254700000981")
        self.bob = make_user("254700000982")
        self._fund(self.alice, "6000", "pg-a")
        self._fund(self.bob, "4000", "pg-b")

    def _fund(self, member, amount, key):
        post_journal(idempotency_key=key, op_type=pm.Op.CONTRIBUTION,
                     lines=pm.contribution_lines(member=member, fund_type="contribution",
                                                 fund_id=self.cid, gross=Money(amount)))

    def _interest(self, member):
        return economic_interest(member, "contribution", self.cid)

    # ── Pool expense (maker-checked) ─────────────────────────────────────────
    def test_expense_needs_a_second_admin_then_executes(self):
        r = active_client(self.admin).post(
            f"/api/contributions/{self.cid}/pool-expense/",
            {"amount": "1000", "apportion": "pro_rata", "reason": "Venue"}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["status"], "PENDING")
        # Nothing has moved yet — it's only a proposal.
        self.assertEqual(self._interest(self.alice), Decimal("6000.0000"))

        r2 = active_client(self.admin2).post(
            f"/api/contributions/pool-actions/{r.data['id']}/approve/", {}, format="json")
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.data["status"], "EXECUTED")
        self.assertEqual(self._interest(self.alice), Decimal("5400.0000"))
        self.assertEqual(self._interest(self.bob), Decimal("3600.0000"))

    def test_maker_cannot_approve_own_request(self):
        r = active_client(self.admin).post(
            f"/api/contributions/{self.cid}/pool-expense/", {"amount": "1000"}, format="json")
        r2 = active_client(self.admin).post(
            f"/api/contributions/pool-actions/{r.data['id']}/approve/", {}, format="json")
        self.assertEqual(r2.status_code, 403)
        self.assertEqual(self._interest(self.alice), Decimal("6000.0000"))  # unchanged

    def test_non_admin_cannot_propose(self):
        r = active_client(self.alice).post(
            f"/api/contributions/{self.cid}/pool-expense/", {"amount": "100"}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_reject_leaves_positions_untouched(self):
        r = active_client(self.admin).post(
            f"/api/contributions/{self.cid}/pool-expense/", {"amount": "1000"}, format="json")
        r2 = active_client(self.admin2).post(
            f"/api/contributions/pool-actions/{r.data['id']}/reject/",
            {"reason": "not now"}, format="json")
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.data["status"], "REJECTED")
        self.assertEqual(self._interest(self.alice), Decimal("6000.0000"))

    # ── External income (direct) → distribution (maker-checked) ──────────────
    def test_income_is_direct_then_distribution_is_maker_checked(self):
        ri = active_client(self.admin).post(
            f"/api/contributions/{self.cid}/external-income/",
            {"amount": "30000", "source": "Business"}, format="json")
        self.assertEqual(ri.status_code, 201)
        self.assertEqual(account_balance(coa.retained_surplus_account(fund_id=self.cid)),
                         Decimal("30000.0000"))

        rd = active_client(self.admin).post(
            f"/api/contributions/{self.cid}/distribute/",
            {"amount": "30000", "apportion": "pro_rata"}, format="json")
        self.assertEqual(rd.status_code, 201)
        self.assertEqual(self._interest(self.alice), Decimal("6000.0000"))  # not yet

        ra = active_client(self.admin2).post(
            f"/api/contributions/pool-actions/{rd.data['id']}/approve/", {}, format="json")
        self.assertEqual(ra.status_code, 200)
        self.assertEqual(self._interest(self.alice), Decimal("24000.0000"))
        self.assertEqual(self._interest(self.bob), Decimal("16000.0000"))
