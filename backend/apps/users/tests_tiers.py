"""
Two-tier access model tests (ADR-0022) — Phase A.

Covers the derived tier properties, the centralized gate (AccessPolicy /
RequiresTier1), and the structured KYC_REQUIRED envelope. Behavioural regression
for the consolidated money-path checks lives in the contributions suite.
"""
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory

from apps.core.exceptions import KYCRequired, custom_exception_handler
from apps.users.models import KYCProfile
from apps.users.permissions import RequiresTier1
from apps.users.tiers import AccessPolicy

User = get_user_model()


def make_user(phone, *, phone_verified=True, kyc=None):
    u = User.objects.create(phone_number=phone, is_phone_verified=phone_verified)
    if kyc:
        KYCProfile.objects.create(
            user=u, status=kyc, given_names="T", surname="U",
            id_number=f"ID{u.pk}", date_of_birth=date(1990, 1, 1),
        )
    return u


class TierDerivationTests(TestCase):
    def test_no_kyc_is_tier0(self):
        u = make_user("254700000001")
        self.assertEqual(u.kyc_status, "not_submitted")
        self.assertTrue(u.is_tier0)
        self.assertFalse(u.is_tier1)
        self.assertFalse(u.has_full_access())

    def test_pending_and_rejected_are_tier0(self):
        for i, s in enumerate(("pending", "rejected"), start=2):
            u = make_user(f"25470000000{i}", kyc=s)
            self.assertTrue(u.is_tier0, s)
            self.assertFalse(u.is_tier1, s)

    def test_approved_kyc_is_tier1(self):
        u = make_user("254700000010", kyc="approved")
        self.assertTrue(u.is_tier1)
        self.assertTrue(u.has_full_access())
        self.assertFalse(u.is_tier0)

    def test_approved_kyc_but_phone_unverified_is_not_tier1(self):
        u = make_user("254700000011", phone_verified=False, kyc="approved")
        self.assertFalse(u.is_tier1)


class AccessPolicyGateTests(TestCase):
    def test_require_tier1_raises_kyc_required_for_tier0(self):
        u = make_user("254700000020", kyc="pending")
        with self.assertRaises(KYCRequired):
            AccessPolicy.require_tier1(u)

    def test_require_tier1_passes_for_tier1(self):
        u = make_user("254700000021", kyc="approved")
        AccessPolicy.require_tier1(u)  # must not raise

    def test_staff_and_superuser_bypass(self):
        staff = make_user("254700000022")
        staff.is_staff = True
        AccessPolicy.require_tier1(staff)  # must not raise
        su = make_user("254700000023")
        su.is_superuser = True
        AccessPolicy.require_tier1(su)  # must not raise

    def test_custom_message_carried_through(self):
        u = make_user("254700000024")
        try:
            AccessPolicy.require_tier1(u, "Verify to contribute.")
        except KYCRequired as e:
            self.assertEqual(e.message, "Verify to contribute.")
            self.assertEqual(e.code, "KYC_REQUIRED")
            self.assertEqual(e.next_step, "/kyc/start")
        else:
            self.fail("KYCRequired not raised")


class KYCRequiredEnvelopeTests(TestCase):
    def test_handler_renders_structured_403(self):
        resp = custom_exception_handler(KYCRequired(), {})
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.data["code"], "KYC_REQUIRED")
        self.assertEqual(resp.data["next_step"], "/kyc/start")
        self.assertIn("message", resp.data)
        # Not the generic PermissionDenied shape
        self.assertNotIn("error", resp.data)


class MoneyPathRegressionTests(TestCase):
    """The consolidated service gate blocks Tier-0 before any money logic runs."""

    def test_contribute_blocks_tier0_with_kyc_required(self):
        from apps.contributions.services.contribution import ContributionService
        u = make_user("254700000040")  # no KYC → Tier 0
        # The tier gate runs before the contribution is even fetched, so a dummy
        # id is fine — we assert the block, not the money path.
        with self.assertRaises(KYCRequired):
            ContributionService.contribute(u, 999999, 100)

    def test_request_advance_blocks_tier0_with_kyc_required(self):
        from datetime import date, timedelta
        from apps.contributions.services.advances import EmergencyAdvanceService
        u = make_user("254700000041")  # no KYC → Tier 0
        with self.assertRaises(KYCRequired):
            EmergencyAdvanceService.request_advance(
                999999, u, 100, 0, date.today() + timedelta(days=30))


class EnforcementFlagTests(TestCase):
    """`gate()` is flag-aware; `require_tier1()` is unconditional."""

    def test_gate_is_noop_when_enforcement_off(self):
        # default: ACCESS_TIER_ENFORCEMENT is off
        AccessPolicy.gate(make_user("254700000050"))  # Tier 0, must not raise

    @override_settings(ACCESS_TIER_ENFORCEMENT=True)
    def test_gate_enforces_when_on(self):
        with self.assertRaises(KYCRequired):
            AccessPolicy.gate(make_user("254700000051"))  # Tier 0 → blocked
        AccessPolicy.gate(make_user("254700000052", kyc="approved"))  # Tier 1 → ok

    def test_require_tier1_always_enforces_regardless_of_flag(self):
        # Even with the flag off, the money-path gate blocks Tier 0.
        with self.assertRaises(KYCRequired):
            AccessPolicy.require_tier1(make_user("254700000053"))


@override_settings(ACCESS_TIER_ENFORCEMENT=True)
class PhaseBServiceGateTests(TestCase):
    """With enforcement on, the new write surfaces reject Tier 0."""

    def test_create_community_blocks_tier0(self):
        from apps.communities.services import CommunityService
        with self.assertRaises(KYCRequired):
            CommunityService.create_community(make_user("254700000060"), {"name": "X"})

    def test_create_community_allows_tier1(self):
        from apps.communities.services import CommunityService
        c = CommunityService.create_community(
            make_user("254700000061", kyc="approved"), {"name": "Chama"})
        self.assertIsNotNone(c.id)

    def test_request_to_join_blocks_tier0(self):
        from apps.communities.services import CommunityService
        owner = make_user("254700000062", kyc="approved")
        community = CommunityService.create_community(owner, {"name": "Chama"})
        with self.assertRaises(KYCRequired):
            CommunityService.request_to_join(make_user("254700000063"), community)

    # The remaining gates are the first statement in their service method, so a
    # Tier 0 user is rejected before any row is fetched — placeholder ids suffice.
    def test_disbursement_request_blocks_tier0(self):
        from apps.contributions.services.disbursement import DisbursementService
        with self.assertRaises(KYCRequired):
            DisbursementService.create_request(999999, make_user("254700000064"), 100, "r", None)

    def test_disbursement_vote_blocks_tier0(self):
        from apps.contributions.services.disbursement import DisbursementService
        with self.assertRaises(KYCRequired):
            DisbursementService.vote(999999, make_user("254700000065"), "APPROVE")

    def test_amendment_propose_blocks_tier0(self):
        from apps.contributions.services.amendments import AmendmentService
        with self.assertRaises(KYCRequired):
            AmendmentService.propose(999999, make_user("254700000066"), {}, "r")

    def test_amendment_vote_blocks_tier0(self):
        from apps.contributions.services.amendments import AmendmentService
        with self.assertRaises(KYCRequired):
            AmendmentService.vote(999999, make_user("254700000067"), "APPROVE")

    def test_standing_order_blocks_tier0(self):
        from apps.contributions.services.standing_orders import StandingOrderService
        with self.assertRaises(KYCRequired):
            StandingOrderService.create_standing_order(make_user("254700000068"), 999999, {})

    def test_welfare_claim_blocks_tier0(self):
        from apps.contributions.services.welfare import WelfareService
        with self.assertRaises(KYCRequired):
            WelfareService.submit_claim(999999, make_user("254700000069"), 100, "r")


@override_settings(ACCESS_TIER_ENFORCEMENT=True)
class RequiresTier1PermissionTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    def _check(self, user):
        req = self.factory.get("/x")
        req.user = user
        return RequiresTier1().has_permission(req, view=None)

    def test_tier1_granted(self):
        self.assertTrue(self._check(make_user("254700000030", kyc="approved")))

    def test_tier0_raises_kyc_required(self):
        with self.assertRaises(KYCRequired):
            self._check(make_user("254700000031", kyc="pending"))

    def test_anonymous_denied_without_raising(self):
        from django.contrib.auth.models import AnonymousUser
        self.assertFalse(self._check(AnonymousUser()))
