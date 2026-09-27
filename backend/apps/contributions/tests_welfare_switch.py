"""Standing welfare funds are off by default (ADR-0027 §0.2).

Off stops anything new going in: no new fund, premium or claim. A fund that
already exists can still be read, have its open claims decided and be wound
up, so no money is ever stuck behind the switch.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.communities.models import Community, CommunityMembership
from apps.communities.services import CommunityService
from apps.contributions.models import WelfareFund, WelfareWindUp
from apps.contributions.services import (
    WelfareService, WelfareWindUpService,
)
from apps.ledger import coa
from apps.ledger.balances import fund_balance

User = get_user_model()


def _verified(phone):
    from apps.verification.models import KYCProfile
    user = User.objects.create(phone_number=phone, is_phone_verified=True)
    KYCProfile.objects.create(
        user=user, status="approved", given_names="Test", surname="User",
        id_number=f"ID{user.pk}", date_of_birth=date(1990, 1, 1),
    )
    return user


def _client(user):
    from apps.users.auth import STAGE_ACTIVE, STAGE_CLAIM
    token = AccessToken.for_user(user)
    token[STAGE_CLAIM] = STAGE_ACTIVE
    client = APIClient()
    client.force_authenticate(user=user, token=token)
    return client


class WelfareSwitchedOffTests(TestCase):
    def setUp(self):
        coa.seed_chart_of_accounts()
        self.admin = _verified("+254700000970")
        self.treasurer = _verified("+254700000971")
        self.alice = _verified("+254700000972")

    def test_off_by_default(self):
        from django.conf import settings
        self.assertFalse(settings.WELFARE_FUND_ENABLED)

    def test_no_new_community_gets_a_welfare_fund(self):
        with self.assertRaises(ValidationError):
            CommunityService.create_community(
                self.admin, {"name": "No Welfare", "has_welfare_fund": True})
        self.assertFalse(Community.objects.filter(name="No Welfare").exists())
        resp = _client(self.admin).post(
            "/api/communities/create/", {"name": "No Welfare", "has_welfare_fund": True}, format="json")
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertFalse(WelfareFund.objects.exists())

    def test_existing_community_cannot_switch_one_on_or_create_one_by_reading(self):
        community = CommunityService.create_community(self.admin, {"name": "Plain Group"})
        with self.assertRaises(Exception):
            CommunityService.update_settings(self.admin, community, {"has_welfare_fund": True})
        resp = _client(self.admin).get(f"/api/contributions/welfare/{community.id}/")
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertFalse(WelfareFund.objects.exists())

    def _existing_fund(self):
        with override_settings(WELFARE_FUND_ENABLED=True):
            community = CommunityService.create_community(
                self.admin, {"name": "Old Welfare", "has_welfare_fund": True})
            type(community).objects.filter(pk=community.pk).update(cooling_off_days=0)
            community.refresh_from_db()
            for user in (self.treasurer, self.alice):
                CommunityService.join_community(user, community)
            CommunityMembership.objects.filter(
                community=community, user=self.treasurer).update(role="admin")
            fund = WelfareService.get_or_create_community_fund(community)
            WelfareService.contribute_to_welfare(fund.id, self.alice, Decimal("600"), "OLD1")
        return community, fund

    def test_existing_fund_takes_no_new_premium_push_or_claim(self):
        community, fund = self._existing_fund()
        resp = _client(self.alice).post("/api/mpesa/stk/push/", {
            "payment_type": "welfare", "community_id": community.id, "amount": "100",
        }, format="json")
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("switched off", resp.json()["error"])
        with self.assertRaises(ValidationError):
            WelfareService.submit_claim(fund.id, self.alice, Decimal("100"), "Hospital")

    def test_existing_fund_is_readable_and_can_be_wound_up(self):
        community, fund = self._existing_fund()
        resp = _client(self.alice).get(f"/api/contributions/welfare/{community.id}/")
        self.assertEqual(resp.status_code, 200, resp.content)
        req = WelfareWindUpService.request(self.admin, fund.id)
        WelfareWindUpService.approve(self.treasurer, req.id)
        req.refresh_from_db()
        self.assertEqual(req.status, WelfareWindUp.Status.EXECUTED)
        self.assertEqual(fund_balance("welfare", fund.id), Decimal("0"))

    def test_a_premium_already_paid_still_settles(self):
        # The M-Pesa callback for money already taken must never be refused.
        community, fund = self._existing_fund()
        WelfareService.contribute_to_welfare(fund.id, self.alice, Decimal("50"), "LATE1")
        self.assertEqual(fund_balance("welfare", fund.id), Decimal("650"))
