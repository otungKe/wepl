"""Winding up a welfare fund splits what is left per head among the members who
are paid up (ADR-0027 §0.2).

Paid up means every month's premium paid to date, read from the premium
journals. One admin proposes, a different one approves; nothing moves before.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.communities.models import CommunityMembership
from apps.communities.services import CommunityService
from apps.contributions.models import WelfareFund, WelfareWindUp, WelfareWindUpPayout
from apps.contributions.services import WelfareService, WelfareWindUpService
from apps.ledger import coa
from apps.ledger.balances import account_balance, fund_balance, trial_balance
from apps.ledger.models import FinancialTransaction
from apps.ledger.posting import reverse_financial_transaction

User = get_user_model()


def _verified(phone):
    from apps.verification.models import KYCProfile
    user = User.objects.create(phone_number=phone, is_phone_verified=True)
    KYCProfile.objects.create(
        user=user, status="approved", given_names="Test", surname="User",
        id_number=f"ID{user.pk}", date_of_birth=date(1990, 1, 1),
    )
    return user


class WelfareWindUpTests(TestCase):
    def setUp(self):
        coa.seed_chart_of_accounts()
        self.admin = _verified("+254700000940")
        self.treasurer = _verified("+254700000941")
        self.alice = _verified("+254700000942")
        self.bob = _verified("+254700000943")
        self.carol = _verified("+254700000944")
        self.community = CommunityService.create_community(
            self.admin, {"name": "Welfare Wind-up", "has_welfare_fund": True})
        type(self.community).objects.filter(pk=self.community.pk).update(cooling_off_days=0)
        self.community.refresh_from_db()
        for user in (self.treasurer, self.alice, self.bob, self.carol):
            CommunityService.join_community(user, self.community)
        CommunityMembership.objects.filter(
            community=self.community, user__in=[self.admin, self.treasurer]).update(role="admin")
        self.fund = WelfareService.get_or_create_community_fund(self.community)
        WelfareFund.objects.filter(pk=self.fund.pk).update(monthly_contribution=Decimal("500"))
        self.fund.refresh_from_db()
        # This month's premium is 500. Alice 500 · Bob 300 (short) · Carol 1,000.
        self._premium(self.alice, "500", "A1")
        self._premium(self.bob, "300", "B1")
        self._premium(self.carol, "1000", "C1")

    def _premium(self, user, amount, receipt):
        WelfareService.contribute_to_welfare(self.fund.id, user, Decimal(amount), receipt)

    def _backdate(self, months):
        then = timezone.now() - timedelta(days=31 * months)
        WelfareFund.objects.filter(pk=self.fund.pk).update(created_at=then)
        CommunityMembership.objects.filter(community=self.community).update(joined_at=then)
        self.fund.refresh_from_db()

    def _wind_up(self):
        req = WelfareWindUpService.request(self.admin, self.fund.id)
        WelfareWindUpService.approve(self.treasurer, req.id)
        req.refresh_from_db()
        return req

    def _paid(self):
        return {p.member_id: p.amount for p in WelfareWindUpPayout.objects.all()}

    def test_paid_up_means_this_months_premium_is_covered(self):
        self.assertEqual(
            [u.id for u in WelfareWindUpService.paid_up_members(self.fund)],
            [self.alice.id, self.carol.id])

    def test_every_month_to_date_must_be_covered(self):
        self._backdate(2)   # three months due: 1,500
        self._premium(self.alice, "1000", "A2")
        self.assertEqual(
            [u.id for u in WelfareWindUpService.paid_up_members(self.fund)], [self.alice.id])

    def test_proposal_moves_nothing(self):
        req = WelfareWindUpService.request(self.admin, self.fund.id)
        self.assertEqual(req.status, WelfareWindUp.Status.PENDING)
        self.assertEqual(req.amount, Decimal("1800"))
        self.assertEqual(fund_balance("welfare", self.fund.id), Decimal("1800"))
        self.assertIsNone(WelfareFund.objects.get(pk=self.fund.pk).closed_at)

    def test_leftover_is_split_per_head_among_paid_up_members(self):
        req = self._wind_up()
        self.assertEqual(req.status, WelfareWindUp.Status.EXECUTED)
        # Carol paid twice what Alice did; each gets the same. Bob is not paid up.
        self.assertEqual(self._paid(), {self.alice.id: Decimal("900"), self.carol.id: Decimal("900")})
        self.assertEqual(fund_balance("welfare", self.fund.id), Decimal("0"))
        self.assertEqual(account_balance(coa.mpesa_float_account()), Decimal("0"))
        self.assertIsNotNone(WelfareFund.objects.get(pk=self.fund.pk).closed_at)
        ft = FinancialTransaction.objects.get(
            context_type="welfare_wind_up", initiated_by=self.alice)
        self.assertEqual(ft.op_type, FinancialTransaction.OpType.WELFARE_CLAIM)
        self.assertTrue(trial_balance()["balanced"])

    def test_split_is_exact_to_the_cent(self):
        self._premium(self.alice, "0.01", "A3")   # 1,800.01 between two
        self._wind_up()
        self.assertEqual(sum(self._paid().values()), Decimal("1800.01"))

    def test_a_reversed_premium_does_not_count(self):
        ft = FinancialTransaction.objects.get(idempotency_key=f"welfare-contrib-{self.fund.id}-{self.alice.id}-A1")
        reverse_financial_transaction(ft, note="charged back")
        self.assertEqual(
            [u.id for u in WelfareWindUpService.paid_up_members(self.fund)], [self.carol.id])

    def test_no_premium_set_counts_every_active_member(self):
        WelfareFund.objects.filter(pk=self.fund.pk).update(monthly_contribution=Decimal("0"))
        self.fund.refresh_from_db()
        self.assertEqual(len(WelfareWindUpService.paid_up_members(self.fund)), 5)

    def test_proposer_cannot_approve_and_members_cannot_propose(self):
        req = WelfareWindUpService.request(self.admin, self.fund.id)
        with self.assertRaises(PermissionDenied):
            WelfareWindUpService.approve(self.admin, req.id)
        with self.assertRaises(PermissionDenied):
            WelfareWindUpService.approve(self.alice, req.id)
        with self.assertRaises(PermissionDenied):
            WelfareWindUpService.request(self.alice, self.fund.id)
        self.assertEqual(fund_balance("welfare", self.fund.id), Decimal("1800"))

    def test_rejected_proposal_leaves_the_fund_open(self):
        req = WelfareWindUpService.request(self.admin, self.fund.id)
        WelfareWindUpService.reject(self.treasurer, req.id)
        self.assertEqual(fund_balance("welfare", self.fund.id), Decimal("1800"))
        self.assertIsNone(WelfareFund.objects.get(pk=self.fund.pk).closed_at)

    def test_open_claims_must_be_decided_first(self):
        WelfareService.submit_claim(self.fund.id, self.bob, Decimal("100"), "Hospital")
        with self.assertRaises(ValidationError):
            WelfareWindUpService.request(self.admin, self.fund.id)

    def test_nobody_paid_up_refuses(self):
        self._backdate(12)
        with self.assertRaises(ValidationError):
            WelfareWindUpService.request(self.admin, self.fund.id)

    def test_closed_fund_takes_no_claims_or_second_wind_up(self):
        self._wind_up()
        self.fund.refresh_from_db()
        with self.assertRaises(ValidationError):
            WelfareService.submit_claim(self.fund.id, self.bob, Decimal("1"), "x")
        with self.assertRaises(ValidationError):
            WelfareWindUpService.request(self.admin, self.fund.id)

    def test_failed_payout_puts_the_share_back_and_is_marked(self):
        from apps.contributions.settlement_targets import _welfare_wind_up_failed
        self._wind_up()
        payout = WelfareWindUpPayout.objects.get(member=self.alice)
        ft = FinancialTransaction.objects.get(context_type="welfare_wind_up", context_id=payout.id)
        reverse_financial_transaction(ft, note="payout failed")
        _welfare_wind_up_failed(payout.id)
        payout.refresh_from_db()
        self.assertEqual(payout.status, WelfareWindUpPayout.Status.FAILED)
        self.assertEqual(fund_balance("welfare", self.fund.id), Decimal("900"))

    def test_endpoints(self):
        from rest_framework.test import APIClient
        from rest_framework_simplejwt.tokens import AccessToken
        from apps.users.auth import STAGE_ACTIVE, STAGE_CLAIM

        def client_for(user):
            token = AccessToken.for_user(user)
            token[STAGE_CLAIM] = STAGE_ACTIVE
            client = APIClient()
            client.force_authenticate(user=user, token=token)
            return client

        url = f"/api/contributions/welfare/{self.community.id}/wind-up/"
        preview = client_for(self.alice).get(url)
        self.assertEqual(preview.status_code, 200, preview.content)
        self.assertEqual(preview.json()["paid_up_members"], "2")
        self.assertEqual(Decimal(preview.json()["per_head"]), Decimal("900"))
        created = client_for(self.admin).post(url, {"reason": "Group dissolving"}, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        decided = client_for(self.treasurer).post(
            f"/api/contributions/welfare/wind-ups/{created.json()['id']}/decide/",
            {"action": "approve"}, format="json")
        self.assertEqual(decided.status_code, 200, decided.content)
        self.assertEqual(decided.json()["status"], "EXECUTED")
