"""A collection gathers money for one named member (ADR-0027 §0.2).

Every pay-in is the beneficiary's, whoever paid it. One admin other than the
beneficiary hands the whole of it over, which closes the collection. Nothing
else takes money out of it.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.communities.models import CommunityMembership
from apps.communities.services import CommunityService
from apps.contributions.models import Contribution, DisbursementRequest, PoolActionRequest
from apps.contributions.services import (
    CollectionService, ContributionService, DisbursementService, EmergencyAdvanceService,
    PoolGovernanceService,
)
from apps.ledger import coa
from apps.ledger.balances import account_balance, fund_balance, member_fund_balance, trial_balance
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


def _client(user):
    from apps.users.auth import STAGE_ACTIVE, STAGE_CLAIM
    token = AccessToken.for_user(user)
    token[STAGE_CLAIM] = STAGE_ACTIVE
    client = APIClient()
    client.force_authenticate(user=user, token=token)
    return client


class CollectionTests(TestCase):
    def setUp(self):
        coa.seed_chart_of_accounts()
        self.admin = _verified("+254700000980")
        self.treasurer = _verified("+254700000981")
        self.alice = _verified("+254700000982")
        self.bob = _verified("+254700000983")
        self.community = CommunityService.create_community(self.admin, {"name": "Collection Chama"})
        type(self.community).objects.filter(pk=self.community.pk).update(cooling_off_days=0)
        self.community.refresh_from_db()
        for user in (self.treasurer, self.alice, self.bob):
            CommunityService.join_community(user, self.community)
        CommunityMembership.objects.filter(
            community=self.community, user=self.treasurer).update(role="treasurer")
        self.c = ContributionService.create_contribution(self.admin, {
            "title": "For Bob's hospital bill", "contribution_type": "COLLECTION",
            "community": self.community, "beneficiary": self.bob,
        }, add_all_members=True)

    def _pay(self, user, amount, receipt):
        ContributionService.contribute(user, self.c.id, Decimal(amount), mpesa_receipt=receipt)

    def _bobs(self):
        return member_fund_balance(self.bob, "contribution", self.c.id)

    def test_every_pay_in_is_the_beneficiarys(self):
        self._pay(self.alice, "700", "A1")
        self._pay(self.admin, "300", "AD1")
        self.assertEqual(self._bobs(), Decimal("1000"))
        self.assertEqual(member_fund_balance(self.alice, "contribution", self.c.id), Decimal("0"))
        # Who paid is still recorded on the transaction.
        self.assertEqual(FinancialTransaction.objects.get(
            idempotency_key=f"contrib-{self.c.id}-A1").initiated_by, self.alice)

    def test_hand_over_pays_everything_and_closes(self):
        self._pay(self.alice, "700", "A1")
        self._pay(self.treasurer, "300", "T1")
        req = CollectionService.hand_over(self.admin, self.c.id)
        self.assertEqual(req.kind, DisbursementRequest.KIND_HANDOVER)
        self.assertEqual(req.status, "EXECUTED")
        self.assertEqual(req.amount, Decimal("1000"))
        self.assertEqual(req.recipient_phone, self.bob.phone_number)
        self.assertEqual(self._bobs(), Decimal("0"))
        self.assertEqual(fund_balance("contribution", self.c.id), Decimal("0"))
        self.assertEqual(account_balance(coa.mpesa_float_account()), Decimal("0"))
        self.c.refresh_from_db()
        self.assertEqual(self.c.status, "closed")
        self.assertTrue(trial_balance()["balanced"])
        with self.assertRaises(ValidationError):
            self._pay(self.alice, "100", "A2")

    def test_beneficiary_cannot_hand_over_to_themselves_and_members_cannot_at_all(self):
        self._pay(self.alice, "500", "A1")
        CommunityMembership.objects.filter(
            community=self.community, user=self.bob).update(role="admin")
        with self.assertRaises(PermissionDenied):
            CollectionService.hand_over(self.bob, self.c.id)
        with self.assertRaises(PermissionDenied):
            CollectionService.hand_over(self.alice, self.c.id)
        self.assertEqual(self._bobs(), Decimal("500"))

    def test_nothing_collected_nothing_to_hand_over(self):
        with self.assertRaises(ValidationError):
            CollectionService.hand_over(self.admin, self.c.id)

    def test_failed_hand_over_restores_the_money_and_can_be_sent_again(self):
        self._pay(self.alice, "500", "A1")
        req = CollectionService.hand_over(self.admin, self.c.id)
        ft = FinancialTransaction.objects.get(idempotency_key=f"disb-exec-{req.id}")
        reverse_financial_transaction(ft, note="payout failed")
        self.assertEqual(self._bobs(), Decimal("500"))
        again = CollectionService.hand_over(self.treasurer, self.c.id)
        self.assertNotEqual(again.id, req.id)
        self.assertEqual(again.amount, Decimal("500"))
        self.assertEqual(self._bobs(), Decimal("0"))
        self.assertTrue(trial_balance()["balanced"])

    def test_no_other_way_out(self):
        self._pay(self.alice, "1000", "A1")
        with self.assertRaises(ValidationError):
            DisbursementService.create_request(
                self.c.id, self.alice, Decimal("100"), "Venue", "+254700000999")
        with self.assertRaises(ValidationError):
            DisbursementService.request_exit(self.c.id, self.bob)
        with self.assertRaises(ValidationError):
            EmergencyAdvanceService.request_advance(
                self.c.id, self.bob, Decimal("100"), Decimal("0"),
                timezone.now().date() + timedelta(days=30))
        with self.assertRaises(ValidationError):
            PoolGovernanceService.request(
                self.admin, self.c.id, action=PoolActionRequest.Action.WIND_UP, amount=None)
        with self.assertRaises(ValidationError):
            ContributionService.record_external_income(self.admin, self.c.id, Decimal("50"))
        self.assertEqual(self._bobs(), Decimal("1000"))

    def test_must_name_a_member_of_the_community(self):
        outsider = _verified("+254700000984")
        with self.assertRaises(ValidationError):
            ContributionService.create_contribution(self.admin, {
                "title": "No one", "contribution_type": "COLLECTION", "community": self.community})
        with self.assertRaises(ValidationError):
            ContributionService.create_contribution(self.admin, {
                "title": "Outsider", "contribution_type": "COLLECTION",
                "community": self.community, "beneficiary": outsider})
        with self.assertRaises(ValidationError):
            ContributionService.create_contribution(self.admin, {
                "title": "Pool", "community": self.community, "beneficiary": self.bob})

    def test_endpoints(self):
        created = _client(self.admin).post("/api/contributions/create/", {
            "title": "For Alice", "contribution_type": "COLLECTION",
            "community": self.community.id, "beneficiary": self.alice.id,
            "add_all_members": True,
        }, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        body = created.json()
        self.assertEqual(body["contribution_type"], "COLLECTION")
        self.assertEqual(body["beneficiary"], self.alice.id)
        c = Contribution.objects.get(pk=body["id"])
        ContributionService.contribute(self.bob, c.id, Decimal("250"), mpesa_receipt="B9")
        handed = _client(self.treasurer).post(f"/api/contributions/{c.id}/hand-over/")
        self.assertEqual(handed.status_code, 201, handed.content)
        self.assertEqual(handed.json()["kind"], "handover")
        self.assertEqual(Decimal(handed.json()["amount"]), Decimal("250"))

    def test_rosca_cannot_be_created_through_the_api(self):
        resp = _client(self.admin).post("/api/contributions/create/", {
            "title": "Rota", "contribution_type": "ROSCA", "community": self.community.id,
        }, format="json")
        self.assertEqual(resp.status_code, 400, resp.content)
