"""A leaving member gets their share back by group decision (ADR-0027 §0.4).

The share is a claim on the group, so it is never withdrawn on demand: the
member asks, the group votes as it would on any payout, and must decide within
30 days. Anything the member still owes on an advance is set off against the
share first. A refused member keeps their share until wind-up.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.communities.models import CommunityMembership
from apps.communities.services import CommunityService
from apps.contributions.models import ContributionParticipant, DisbursementRequest
from apps.contributions.services import (
    ContributionService, DisbursementService, EmergencyAdvanceService,
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


class ExitSettlementTests(TestCase):
    def setUp(self):
        coa.seed_chart_of_accounts()
        self.alice = _verified("+254700000960")
        self.bob = _verified("+254700000961")
        self.carol = _verified("+254700000962")
        self.dan = _verified("+254700000963")
        self.community = CommunityService.create_community(self.alice, {"name": "Exit Chama"})
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
        self._fund(self.alice, "6000")
        self._fund(self.bob, "3000")
        self._fund(self.carol, "1000")

    def _fund(self, member, amount):
        post_journal(idempotency_key=f"fund-{member.pk}", op_type=pm.Op.CONTRIBUTION,
                     lines=pm.contribution_lines(member=member, fund_type="contribution",
                                                 fund_id=self.c.id, gross=Money(amount)))

    def _share(self, member):
        return member_fund_balance(member, "contribution", self.c.id)

    def _decide(self, req, choice):
        for voter in (self.alice, self.bob, self.carol):
            req.refresh_from_db()
            if req.status != "PENDING" or voter == req.requested_by:
                continue
            DisbursementService.vote(req.id, voter, choice)
        req.refresh_from_db()
        return req

    def _float(self):
        return account_balance(coa.mpesa_float_account())

    # ── the request itself moves nothing ────────────────────────────────────

    def test_request_quotes_the_share_and_sets_a_30_day_deadline(self):
        req = DisbursementService.request_exit(self.c.id, self.carol)
        self.assertEqual(req.kind, DisbursementRequest.KIND_EXIT)
        self.assertEqual(req.status, "PENDING")
        self.assertEqual(req.amount, Decimal("1000"))
        self.assertAlmostEqual(
            req.decide_by, timezone.now() + timedelta(days=30), delta=timedelta(minutes=1))
        # Nothing is paid until the group decides.
        self.assertEqual(self._share(self.carol), Decimal("1000"))
        self.assertEqual(self._float(), Decimal("10000"))

    def test_approved_exit_pays_the_whole_share_and_ends_membership(self):
        req = self._decide(DisbursementService.request_exit(self.c.id, self.carol), "APPROVE")
        self.assertEqual(req.status, "EXECUTED")
        self.assertEqual(self._share(self.carol), Decimal("0"))
        # Only the leaver's share is drawn down; the others are untouched.
        self.assertEqual(self._share(self.alice), Decimal("6000"))
        self.assertEqual(self._share(self.bob), Decimal("3000"))
        self.assertEqual(self._float(), Decimal("9000"))
        self.assertFalse(ContributionParticipant.objects.get(
            contribution=self.c, user=self.carol).is_active)
        ft = FinancialTransaction.objects.get(idempotency_key=f"disb-exec-{req.id}")
        self.assertEqual(ft.amount, Decimal("1000"))
        self.assertEqual(ft.context_type, "disbursement_request")
        self.assertTrue(trial_balance()["balanced"])

    def test_refused_member_keeps_their_share(self):
        req = self._decide(DisbursementService.request_exit(self.c.id, self.carol), "REJECT")
        self.assertEqual(req.status, "REJECTED")
        self.assertEqual(self._share(self.carol), Decimal("1000"))
        self.assertTrue(ContributionParticipant.objects.get(
            contribution=self.c, user=self.carol).is_active)

    def test_pays_the_share_as_it_stands_when_approved(self):
        req = DisbursementService.request_exit(self.c.id, self.carol)
        # The group spends 1,000 while the request is open: Carol bears 100 of it.
        spend = DisbursementService.create_request(
            self.c.id, self.alice, Decimal("1000"), "Venue", "+254700000999")
        self._decide(spend, "APPROVE")
        req = self._decide(req, "APPROVE")
        self.assertEqual(req.amount, Decimal("900"))
        self.assertEqual(self._share(self.carol), Decimal("0"))
        self.assertTrue(trial_balance()["balanced"])

    def test_failed_payout_restores_the_share(self):
        req = self._decide(DisbursementService.request_exit(self.c.id, self.carol), "APPROVE")
        ft = FinancialTransaction.objects.get(idempotency_key=f"disb-exec-{req.id}")
        reverse_financial_transaction(ft, note="payout failed")
        self.assertEqual(self._share(self.carol), Decimal("1000"))
        self.assertEqual(self._float(), Decimal("10000"))

    def test_member_who_already_left_can_still_ask(self):
        ContributionService.leave_contribution(self.c.id, self.carol)
        req = self._decide(DisbursementService.request_exit(self.c.id, self.carol), "APPROVE")
        self.assertEqual(req.status, "EXECUTED")
        self.assertEqual(self._share(self.carol), Decimal("0"))

    # ── refusals ────────────────────────────────────────────────────────────

    def test_no_share_no_exit_payout(self):
        with self.assertRaises(ValidationError):
            DisbursementService.request_exit(self.c.id, self.dan)

    def test_one_open_exit_at_a_time(self):
        DisbursementService.request_exit(self.c.id, self.carol)
        with self.assertRaises(ValidationError):
            DisbursementService.request_exit(self.c.id, self.carol)

    def test_outsider_cannot_ask(self):
        from django.core.exceptions import PermissionDenied
        stranger = _verified("+254700000964")
        with self.assertRaises(PermissionDenied):
            DisbursementService.request_exit(self.c.id, stranger)

    def test_rosca_settles_through_its_rotation(self):
        rosca = ContributionService.create_contribution(self.alice, {
            "title": "Merry-go-round", "contribution_type": "ROSCA",
            "community": self.community,
        })
        with self.assertRaises(ValidationError):
            DisbursementService.request_exit(rosca.id, self.alice)

    # ── an unpaid advance is set off against the share ──────────────────────

    def _advance_to_bob(self):
        advance = EmergencyAdvanceService.request_advance(
            self.c.id, self.bob, Decimal("1000"), Decimal("10"),
            timezone.now().date() + timedelta(days=30))
        EmergencyAdvanceService.approve_advance(advance.id, self.alice)
        advance.refresh_from_db()
        return advance

    def test_quote_deducts_what_is_owed_with_interest(self):
        self._advance_to_bob()
        quote = DisbursementService.exit_quote(self.c, self.bob)
        self.assertEqual(quote["share"], Decimal("3000"))
        self.assertEqual(quote["owed"], Decimal("1100"))
        self.assertEqual(quote["payout"], Decimal("1900"))

    def test_advance_is_set_off_and_the_rest_paid(self):
        advance = self._advance_to_bob()
        req = self._decide(DisbursementService.request_exit(self.c.id, self.bob), "APPROVE")
        self.assertEqual(req.status, "EXECUTED")
        self.assertEqual(req.amount, Decimal("1900"))
        advance.refresh_from_db()
        self.assertEqual(advance.status, "REPAID")
        self.assertEqual(advance.balance_due, Decimal("0"))
        self.assertEqual(self._share(self.bob), Decimal("0"))
        self.assertEqual(account_balance(
            coa.member_receivable_account(user=self.bob, fund_id=advance.id)), Decimal("0"))
        # The interest Bob owed is the group's surplus, not Wepl's.
        self.assertEqual(account_balance(
            coa.retained_surplus_account(fund_id=self.c.id)), Decimal("100"))
        # 10,000 in, 1,000 lent, 1,900 paid out.
        self.assertEqual(self._float(), Decimal("7100"))
        self.assertEqual(fund_balance("contribution", self.c.id), Decimal("7000"))
        self.assertTrue(trial_balance()["balanced"])

    def test_advance_repaid_in_part_owes_only_the_rest(self):
        advance = self._advance_to_bob()
        EmergencyAdvanceService.repay(advance.id, self.bob, Decimal("600"), "R-PART")
        self.assertEqual(DisbursementService.exit_quote(self.c, self.bob)["owed"], Decimal("500"))
        req = self._decide(DisbursementService.request_exit(self.c.id, self.bob), "APPROVE")
        self.assertEqual(req.amount, Decimal("2500"))
        advance.refresh_from_db()
        self.assertEqual(advance.status, "REPAID")
        self.assertTrue(trial_balance()["balanced"])

    # ── the endpoint ────────────────────────────────────────────────────────

    def test_endpoint_get_quotes_and_post_opens_a_request(self):
        from rest_framework.test import APIClient
        from rest_framework_simplejwt.tokens import AccessToken
        from apps.users.auth import STAGE_ACTIVE, STAGE_CLAIM
        token = AccessToken.for_user(self.carol)
        token[STAGE_CLAIM] = STAGE_ACTIVE
        client = APIClient()
        client.force_authenticate(user=self.carol, token=token)
        url = f"/api/contributions/{self.c.id}/exit/"
        quote = client.get(url)
        self.assertEqual(quote.status_code, 200, quote.content)
        self.assertEqual(Decimal(quote.json()["payout"]), Decimal("1000"))
        created = client.post(url, {}, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.json()["kind"], "exit")
        self.assertIsNotNone(created.json()["decide_by"])
        self.assertEqual(self._share(self.carol), Decimal("1000"))
