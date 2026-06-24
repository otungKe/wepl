"""Contribution authorization-policy tests (ADR-0009).

Verifies that the centralized policy (and the FinancialPermissions implementation
it delegates to) decides authorization the same way the old inline checks did —
both as unit assertions and over the wire after the view migration.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.communities.models import CommunityMembership
from apps.communities.services import CommunityService
from apps.core.policy import can, require
from apps.users.auth import STAGE_ACTIVE, STAGE_CLAIM

from .models import ContributionParticipant
from .services import ContributionService

User = get_user_model()
Role = CommunityMembership.Role


def make_user(phone):
    u = User.objects.create(phone_number=phone)
    u.set_pin("123456")
    return u


def active_client(user) -> APIClient:
    token = AccessToken.for_user(user)
    token[STAGE_CLAIM] = STAGE_ACTIVE
    client = APIClient()
    client.force_authenticate(user=user, token=token)
    return client


class ContributionPolicyUnitTests(TestCase):

    def setUp(self):
        self.creator   = make_user("254700000001")  # community creator + contribution creator
        self.admin     = make_user("254700000002")
        self.treasurer = make_user("254700000003")
        self.member    = make_user("254700000004")  # community member, not a participant
        self.participant = make_user("254700000005")
        self.outsider  = make_user("254700000006")

        self.community = CommunityService.create_community(self.creator, {"name": "Chama"})
        CommunityMembership.objects.create(user=self.admin,     community=self.community, role=Role.ADMIN)
        CommunityMembership.objects.create(user=self.treasurer, community=self.community, role=Role.TREASURER)
        CommunityMembership.objects.create(user=self.member,    community=self.community, role=Role.MEMBER)

        self.contribution = ContributionService.create_contribution(
            self.creator, {"title": "Pool", "contribution_type": "POOL",
                           "visibility": "closed", "community": self.community},
        )
        ContributionParticipant.objects.create(
            contribution=self.contribution, user=self.participant, is_active=True)

    # ── contribution.admin: creator OR community admin/treasurer ──────────────
    def test_admin_capability(self):
        for u in (self.creator, self.admin, self.treasurer):
            self.assertTrue(can(u, "contribution.admin", self.contribution), u.phone_number)
        for u in (self.member, self.participant, self.outsider):
            self.assertFalse(can(u, "contribution.admin", self.contribution), u.phone_number)

    # ── contribution.participate: active participants only ────────────────────
    def test_participate_capability(self):
        self.assertTrue(can(self.participant, "contribution.participate", self.contribution))
        # the creator is auto-enrolled as a participant on creation
        self.assertTrue(can(self.creator, "contribution.participate", self.contribution))
        # community members who never joined the contribution, and outsiders, are not
        self.assertFalse(can(self.member, "contribution.participate", self.contribution))
        self.assertFalse(can(self.outsider, "contribution.participate", self.contribution))

    # ── contribution.view: creator OR active participant ──────────────────────
    def test_view_capability(self):
        self.assertTrue(can(self.creator, "contribution.view", self.contribution))
        self.assertTrue(can(self.participant, "contribution.view", self.contribution))
        self.assertFalse(can(self.member, "contribution.view", self.contribution))
        self.assertFalse(can(self.outsider, "contribution.view", self.contribution))

    # ── contribution.lifecycle: creator only ─────────────────────────────────
    def test_lifecycle_capability_is_creator_only(self):
        self.assertTrue(can(self.creator, "contribution.lifecycle", self.contribution))
        self.assertFalse(can(self.admin, "contribution.lifecycle", self.contribution))

    # ── community.finance.manage: admins & treasurers (mirrors is_community_admin) ──
    def test_community_finance_manage(self):
        for u in (self.creator, self.admin, self.treasurer):
            self.assertTrue(can(u, "community.finance.manage", self.community), u.phone_number)
        for u in (self.member, self.outsider):
            self.assertFalse(can(u, "community.finance.manage", self.community), u.phone_number)

    def test_require_and_anonymous(self):
        with self.assertRaises(PermissionDenied):
            require(self.member, "contribution.admin", self.contribution)
        self.assertFalse(can(AnonymousUser(), "contribution.view", self.contribution))

    def test_policy_matches_financial_permissions_implementation(self):
        # The policy must not diverge from the helper it delegates to.
        from apps.ledger.permissions import FinancialPermissions
        for u in (self.creator, self.admin, self.member, self.participant, self.outsider):
            self.assertEqual(
                can(u, "contribution.admin", self.contribution),
                FinancialPermissions.is_contribution_admin(self.contribution, u),
                u.phone_number,
            )


class ContributionAuthzApiTests(TestCase):

    def setUp(self):
        self.creator  = make_user("254700000001")
        self.member   = make_user("254700000002")   # community member, not contribution participant
        self.outsider = make_user("254700000003")
        self.community = CommunityService.create_community(self.creator, {"name": "Chama"})
        CommunityMembership.objects.create(user=self.member, community=self.community, role=Role.MEMBER)
        self.contribution = ContributionService.create_contribution(
            self.creator, {"title": "Pool", "contribution_type": "POOL",
                           "visibility": "closed", "community": self.community},
        )

    def test_non_admin_cannot_edit_contribution(self):
        r = active_client(self.member).patch(
            f"/api/contributions/{self.contribution.id}/update/",
            {"title": "Hacked"}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_creator_can_edit_contribution(self):
        r = active_client(self.creator).patch(
            f"/api/contributions/{self.contribution.id}/update/",
            {"title": "Renamed"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.contribution.refresh_from_db()
        self.assertEqual(self.contribution.title, "Renamed")

    def test_non_member_cannot_list_community_contributions(self):
        r = active_client(self.outsider).get(
            f"/api/contributions/community/{self.community.id}/")
        self.assertEqual(r.status_code, 403)

    def test_member_can_list_community_contributions(self):
        r = active_client(self.member).get(
            f"/api/contributions/community/{self.community.id}/")
        self.assertEqual(r.status_code, 200)

    def test_non_admin_cannot_view_join_request_queue(self):
        r = active_client(self.member).get(
            f"/api/contributions/{self.contribution.id}/join-requests/")
        self.assertEqual(r.status_code, 403)


class GovernanceVotingPolicyTests(TestCase):
    """contribution.vote_disbursement / vote_amendment threshold logic."""

    def setUp(self):
        self.creator   = make_user("254700000001")
        self.admin     = make_user("254700000002")
        self.treasurer = make_user("254700000003")
        self.participant = make_user("254700000004")  # plain participant (not community admin)
        self.outsider  = make_user("254700000005")

        self.community = CommunityService.create_community(self.creator, {"name": "Chama"})
        CommunityMembership.objects.create(user=self.admin,     community=self.community, role=Role.ADMIN)
        CommunityMembership.objects.create(user=self.treasurer, community=self.community, role=Role.TREASURER)
        CommunityMembership.objects.create(user=self.participant, community=self.community, role=Role.MEMBER)
        # admin is NOT a participant; treasurer IS a participant (to exercise the nuance)
        self.contribution = ContributionService.create_contribution(
            self.creator, {"title": "Pool", "contribution_type": "POOL",
                           "visibility": "closed", "community": self.community},
        )
        ContributionParticipant.objects.create(
            contribution=self.contribution, user=self.participant, is_active=True)
        ContributionParticipant.objects.create(
            contribution=self.contribution, user=self.treasurer, is_active=True)

    def _set(self, **kw):
        for k, v in kw.items():
            setattr(self.contribution, k, v)
        self.contribution.save(update_fields=list(kw))

    def test_disbursement_admins_threshold(self):
        self._set(voting_threshold="admins")
        # admins/treasurers/creator may vote — participant status NOT required
        self.assertTrue(can(self.admin, "contribution.vote_disbursement", self.contribution))
        self.assertTrue(can(self.treasurer, "contribution.vote_disbursement", self.contribution))
        self.assertTrue(can(self.creator, "contribution.vote_disbursement", self.contribution))
        # a plain participant cannot
        self.assertFalse(can(self.participant, "contribution.vote_disbursement", self.contribution))
        self.assertFalse(can(self.outsider, "contribution.vote_disbursement", self.contribution))

    def test_disbursement_percentage_threshold(self):
        self._set(voting_threshold="50")
        # any active participant may vote
        self.assertTrue(can(self.participant, "contribution.vote_disbursement", self.contribution))
        self.assertTrue(can(self.creator, "contribution.vote_disbursement", self.contribution))
        # a community admin who is NOT a participant cannot
        self.assertFalse(can(self.admin, "contribution.vote_disbursement", self.contribution))

    def test_amendment_admins_threshold_requires_participant(self):
        self._set(amendment_voting_threshold="admins")
        # treasurer is a community admin AND a participant → may vote
        self.assertTrue(can(self.treasurer, "contribution.vote_amendment", self.contribution))
        self.assertTrue(can(self.creator, "contribution.vote_amendment", self.contribution))
        # admin is a community admin but NOT a participant → may NOT vote on amendments
        # (the preserved amendment-specific nuance vs. disbursements)
        self.assertFalse(can(self.admin, "contribution.vote_amendment", self.contribution))
        self.assertFalse(can(self.participant, "contribution.vote_amendment", self.contribution))

    def test_amendment_percentage_threshold(self):
        self._set(amendment_voting_threshold="67")
        self.assertTrue(can(self.participant, "contribution.vote_amendment", self.contribution))
        self.assertFalse(can(self.admin, "contribution.vote_amendment", self.contribution))


class IsParticipantSerializerFieldTests(TestCase):
    """ContributionSerializer.is_participant lets clients hide a stray 'Join' button
    for contributions the user is already in (mobile bug: phone-string matching)."""

    def setUp(self):
        from .serializers import ContributionSerializer
        from rest_framework.test import APIRequestFactory
        self.SerCls = ContributionSerializer
        self.rf = APIRequestFactory()
        self.creator = make_user("254700000001")
        self.participant = make_user("254700000002")
        self.outsider = make_user("254700000003")
        self.c = ContributionService.create_contribution(
            self.creator, {"title": "Pool", "contribution_type": "POOL", "visibility": "open"})
        ContributionParticipant.objects.create(
            contribution=self.c, user=self.participant, is_active=True)

    def _flag(self, user):
        req = self.rf.get("/")
        req.user = user
        return self.SerCls(self.c, context={"request": req}).data["is_participant"]

    def test_creator_is_participant(self):
        self.assertTrue(self._flag(self.creator))

    def test_active_participant_is_participant(self):
        self.assertTrue(self._flag(self.participant))

    def test_outsider_is_not_participant(self):
        self.assertFalse(self._flag(self.outsider))
