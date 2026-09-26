"""Winding up a pool pays everything out, by group decision (ADR-0027).

The group votes the wind-up under its own threshold. Then debts are set off
against the borrowers' shares, the surplus is shared out by share, every
member is paid, and the pool is closed with nothing left in it.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.communities.models import CommunityMembership
from apps.communities.services import CommunityService
from apps.contributions.models import (
    Contribution, ContributionParticipant, DisbursementRequest, PoolActionRequest,
)
from apps.contributions.services import (
    ContributionService, DisbursementService, EmergencyAdvanceService, PoolGovernanceService,
)
from apps.ledger import coa, posting_map as pm
from apps.ledger.balances import (
    account_balance, fund_balance, member_fund_balance, trial_balance,
)
from apps.ledger.models import FinancialTransaction
from apps.ledger.money import Money
from apps.ledger.posting import post_journal, reverse_financial_transaction

User = get_user_model()


def _verified(phone):
    from apps.verification.models import KYCProfile
    user = User.objects.create(phone_number=phone, is_phone_verified=True)
    KYCProfile.objects.create(
        user=user, status="approved", given_names="Test", surname="User",
        id_number=f"ID{user.pk}", date_of_birth=date(1990, 1, 1),
    )
    return user


class WindUpTests(TestCase):
    def setUp(self):
        coa.seed_chart_of_accounts()
        self.alice = _verified("+254700000950")
        self.bob = _verified("+254700000951")
        self.carol = _verified("+254700000952")
        self.dan = _verified("+254700000953")
        self.community = CommunityService.create_community(self.alice, {"name": "Wind-up Chama"})
        type(self.community).objects.filter(pk=self.community.pk).update(cooling_off_days=0)
        self.community.refresh_from_db()
        for user in (self.bob, self.carol, self.dan):
            CommunityService.join_community(user, self.community)
        CommunityMembership.objects.filter(
            community=self.community, user__in=[self.alice, self.bob, self.carol],
        ).update(role="admin")
        self.c = ContributionService.create_contribution(self.alice, {
            "title": "Pool", "contribution_type": "POOL", "visibility": "closed",
            "community": self.community, "voting_threshold": "50",
        })
        for user in (self.bob, self.carol, self.dan):
            ContributionService.join_contribution(self.c.id, user)
        # Alice 6,000 · Bob 3,000 · Carol 1,000 · Dan nothing.
        for member, amount in ((self.alice, "6000"), (self.bob, "3000"), (self.carol, "1000")):
            post_journal(idempotency_key=f"fund-{member.pk}", op_type=pm.Op.CONTRIBUTION,
                         lines=pm.contribution_lines(member=member, fund_type="contribution",
                                                     fund_id=self.c.id, gross=Money(amount)))

    def _share(self, member):
        return member_fund_balance(member, "contribution", self.c.id)

    def _surplus(self):
        return account_balance(coa.retained_surplus_account(fund_id=self.c.id))

    def _float(self):
        return account_balance(coa.mpesa_float_account())

    def _wind_up(self):
        req = PoolGovernanceService.request(
            self.alice, self.c.id, action=PoolActionRequest.Action.WIND_UP, amount=None)
        for voter in (self.bob, self.carol):
            req.refresh_from_db()
            if req.status == PoolActionRequest.Status.PENDING:
                PoolGovernanceService.approve(voter, req.id)
        req.refresh_from_db()
        return req

    def _payouts(self):
        return {r.requested_by_id: r for r in DisbursementRequest.objects.filter(
            contribution=self.c, kind=DisbursementRequest.KIND_WINDUP)}

    def test_proposal_moves_nothing_and_records_what_the_pool_holds(self):
        req = PoolGovernanceService.request(
            self.alice, self.c.id, action=PoolActionRequest.Action.WIND_UP, amount=None)
        self.assertEqual(req.status, PoolActionRequest.Status.PENDING)
        self.assertEqual(req.amount, Decimal("10000"))
        self.assertEqual(self._float(), Decimal("10000"))
        with self.assertRaises(ValidationError):
            PoolGovernanceService.request(
                self.alice, self.c.id, action=PoolActionRequest.Action.WIND_UP, amount=None)

    def test_everyone_is_paid_their_share_and_the_pool_closes(self):
        req = self._wind_up()
        self.assertEqual(req.status, PoolActionRequest.Status.EXECUTED)
        paid = self._payouts()
        self.assertEqual({uid: r.amount for uid, r in paid.items()}, {
            self.alice.id: Decimal("6000"), self.bob.id: Decimal("3000"),
            self.carol.id: Decimal("1000"),
        })
        self.assertTrue(all(r.status == "EXECUTED" for r in paid.values()))
        self.assertEqual(fund_balance("contribution", self.c.id), Decimal("0"))
        self.assertEqual(self._float(), Decimal("0"))
        self.c.refresh_from_db()
        self.assertEqual(self.c.status, "closed")
        self.assertFalse(ContributionParticipant.objects.filter(
            contribution=self.c, is_active=True).exists())
        self.assertTrue(trial_balance()["balanced"])

    def test_debts_are_set_off_and_the_surplus_shared_by_share(self):
        advance = EmergencyAdvanceService.request_advance(
            self.c.id, self.bob, Decimal("1000"), Decimal("10"),
            timezone.now().date() + timedelta(days=30))
        EmergencyAdvanceService.approve_advance(advance.id, self.alice)
        ContributionService.record_external_income(self.alice, self.c.id, Decimal("500"),
                                                   source="Tent hire")
        self._wind_up()

        advance.refresh_from_db()
        self.assertEqual(advance.status, "REPAID")
        # Shares after set-off: Alice 6,000 · Bob 1,900 · Carol 1,000 = 8,900.
        # Surplus: 500 income + 100 of Bob's interest = 600, shared by share.
        paid = {uid: r.amount for uid, r in self._payouts().items()}
        self.assertEqual(sum(paid.values()), Decimal("9500"))
        self.assertEqual(paid[self.alice.id], Decimal("6404.49"))
        self.assertEqual(paid[self.bob.id], Decimal("2028.09"))
        self.assertEqual(paid[self.carol.id], Decimal("1067.42"))
        # 10,000 in + 500 income − 1,000 lent − 9,500 paid.
        self.assertEqual(self._float(), Decimal("0"))
        self.assertEqual(self._surplus(), Decimal("0"))
        self.assertEqual(fund_balance("contribution", self.c.id), Decimal("0"))
        self.assertTrue(trial_balance()["balanced"])

    def test_refused_exit_is_paid_at_wind_up(self):
        exit_req = DisbursementService.request_exit(self.c.id, self.carol)
        for voter in (self.alice, self.bob):
            exit_req.refresh_from_db()
            if exit_req.status == "PENDING":
                DisbursementService.vote(exit_req.id, voter, "REJECT")
        self._wind_up()
        self.assertEqual(self._payouts()[self.carol.id].amount, Decimal("1000"))
        self.assertEqual(self._share(self.carol), Decimal("0"))

    def test_open_requests_are_cancelled(self):
        exit_req = DisbursementService.request_exit(self.c.id, self.carol)
        expense = PoolGovernanceService.request(
            self.alice, self.c.id, action=PoolActionRequest.Action.EXPENSE, amount=Decimal("100"))
        self._wind_up()
        exit_req.refresh_from_db()
        expense.refresh_from_db()
        self.assertEqual(exit_req.status, "CANCELLED")
        self.assertEqual(expense.status, PoolActionRequest.Status.CANCELLED)

    def test_failed_payout_restores_that_members_share(self):
        self._wind_up()
        req = self._payouts()[self.bob.id]
        ft = FinancialTransaction.objects.get(idempotency_key=f"disb-exec-{req.id}")
        reverse_financial_transaction(ft, note="payout failed")
        self.assertEqual(self._share(self.bob), Decimal("3000"))

    def test_not_carried_out_without_the_group(self):
        req = PoolGovernanceService.request(
            self.alice, self.c.id, action=PoolActionRequest.Action.WIND_UP, amount=None)
        PoolGovernanceService.approve(self.bob, req.id)
        req.refresh_from_db()
        self.assertEqual(req.status, PoolActionRequest.Status.PENDING)   # 50% needs two
        self.assertEqual(self._float(), Decimal("10000"))
        with self.assertRaises(PermissionDenied):
            PoolGovernanceService.request(
                self.dan, self.c.id, action=PoolActionRequest.Action.WIND_UP, amount=None)

    def test_refused_while_a_debt_exceeds_its_share(self):
        advance = EmergencyAdvanceService.request_advance(
            self.c.id, self.carol, Decimal("800"), Decimal("10"),
            timezone.now().date() + timedelta(days=30))
        EmergencyAdvanceService.approve_advance(advance.id, self.alice)
        # Group spending shrinks Carol's share below the 880 she owes.
        post_journal(idempotency_key="shrink", op_type=pm.Op.POOL_EXPENSE,
                     lines=pm.pool_expense_lines(fund_type="contribution", fund_id=self.c.id,
                                                 allocations=[pm.Allocation(self.carol, Money("300"))]))
        with self.assertRaises(ValidationError):
            PoolGovernanceService.request(
                self.alice, self.c.id, action=PoolActionRequest.Action.WIND_UP, amount=None)

    def test_rosca_is_not_wound_up_this_way(self):
        rosca = ContributionService.create_contribution(self.alice, {
            "title": "Merry-go-round", "contribution_type": "ROSCA", "community": self.community,
        })
        with self.assertRaises(ValidationError):
            PoolGovernanceService.request(
                self.alice, rosca.id, action=PoolActionRequest.Action.WIND_UP, amount=None)

    def test_endpoint_proposes_a_wind_up(self):
        from rest_framework.test import APIClient
        from rest_framework_simplejwt.tokens import AccessToken
        from apps.users.auth import STAGE_ACTIVE, STAGE_CLAIM
        token = AccessToken.for_user(self.alice)
        token[STAGE_CLAIM] = STAGE_ACTIVE
        client = APIClient()
        client.force_authenticate(user=self.alice, token=token)
        resp = client.post(f"/api/contributions/{self.c.id}/wind-up/", {"reason": "Done"}, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.json()["action"], "WIND_UP")
        self.assertEqual(Decimal(resp.json()["amount"]), Decimal("10000"))
