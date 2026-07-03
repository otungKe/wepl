"""
Two-tier access model tests (ADR-0022) — Phase A.

Covers the derived tier properties, the centralized gate (AccessPolicy /
RequiresTier1), and the structured KYC_REQUIRED envelope. Behavioural regression
for the consolidated money-path checks lives in the contributions suite.
"""
from datetime import date

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
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
