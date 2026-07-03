"""STK push: Tier-1 gate + target-number selection + per-user throttle."""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APITestCase

from apps.contributions.services import ContributionService
from apps.mpesa.models import MpesaSTKRequest
from apps.payments.providers import registry
from apps.payments.providers.fake import FakeProvider
from apps.users.models import KYCProfile

User = get_user_model()
URL = "/api/mpesa/stk/push/"


def _make_tier1(user):
    """Approve KYC + phone-verify a user so they clear the Tier-1 money gate."""
    if not user.is_phone_verified:
        user.is_phone_verified = True
        user.save(update_fields=["is_phone_verified"])
    KYCProfile.objects.create(
        user=user, status="approved",
        given_names="Test", surname="User",
        id_number=f"ID{user.pk}", date_of_birth=date(1990, 1, 1),
    )
    return user


class STKPushTargetNumberTests(APITestCase):
    def setUp(self):
        registry.use_provider(FakeProvider())
        cache.clear()  # reset throttle history between tests
        self.user = _make_tier1(User.objects.create(phone_number="254700000001"))
        self.client.force_authenticate(self.user)
        self.contribution = ContributionService.create_contribution(
            self.user, {"title": "Pool", "contribution_type": "POOL", "visibility": "open"})

    def tearDown(self):
        registry.use_provider(None)

    def _push(self, **extra):
        body = {"payment_type": "contribution", "contribution_id": self.contribution.id,
                "amount": 10, **extra}
        return self.client.post(URL, body, format="json")

    def test_defaults_to_caller_phone(self):
        r = self._push()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(MpesaSTKRequest.objects.latest("id").phone_number, "254700000001")

    def test_uses_body_phone_when_provided(self):
        r = self._push(phone_number="0712345678")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(MpesaSTKRequest.objects.latest("id").phone_number, "254712345678")

    def test_normalizes_plus_format(self):
        r = self._push(phone_number="+254711111111")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(MpesaSTKRequest.objects.latest("id").phone_number, "254711111111")

    def test_invalid_phone_rejected(self):
        for bad in ("abc", "12345", "254812345678"):  # non-numeric / short / wrong prefix
            r = self._push(phone_number=bad)
            self.assertEqual(r.status_code, 400, bad)


class STKPushThrottleTests(APITestCase):
    def setUp(self):
        registry.use_provider(FakeProvider())
        cache.clear()
        self.user = _make_tier1(User.objects.create(phone_number="254700000002"))
        self.client.force_authenticate(self.user)
        self.contribution = ContributionService.create_contribution(
            self.user, {"title": "Pool", "contribution_type": "POOL", "visibility": "open"})

    def tearDown(self):
        registry.use_provider(None)
        cache.clear()

    def test_per_user_rate_limit(self):
        body = {"payment_type": "contribution", "contribution_id": self.contribution.id, "amount": 10}
        # default 'stk_push' rate is 5/minute
        statuses = [self.client.post(URL, body, format="json").status_code for _ in range(6)]
        self.assertEqual(statuses[:5], [200] * 5)
        self.assertEqual(statuses[5], 429)


class STKPushTierGateTests(APITestCase):
    """STK push is the single money front-door — Tier-0 (unverified) users are
    blocked with a structured KYC_REQUIRED 403, regardless of the enforcement
    flag (money paths are always gated, ADR-0022)."""

    def setUp(self):
        registry.use_provider(FakeProvider())
        cache.clear()
        # Creator is Tier-1 so the pool can be created and paid into by others.
        self.owner = _make_tier1(User.objects.create(phone_number="254700000010"))
        self.client.force_authenticate(self.owner)
        self.contribution = ContributionService.create_contribution(
            self.owner, {"title": "Pool", "contribution_type": "POOL", "visibility": "open"})

    def tearDown(self):
        registry.use_provider(None)
        cache.clear()

    def _push(self, **extra):
        body = {"payment_type": "contribution", "contribution_id": self.contribution.id,
                "amount": 10, **extra}
        return self.client.post(URL, body, format="json")

    def test_tier0_user_blocked(self):
        tier0 = User.objects.create(phone_number="254700000011")  # no KYC → Tier 0
        self.client.force_authenticate(tier0)
        r = self._push()
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data.get("code"), "KYC_REQUIRED")

    def test_tier1_user_allowed(self):
        r = self._push()
        self.assertEqual(r.status_code, 200)
