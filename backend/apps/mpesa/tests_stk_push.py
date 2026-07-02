"""STK push: target-number selection + per-user throttle."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APITestCase

from apps.contributions.services import ContributionService
from apps.mpesa.models import MpesaSTKRequest
from apps.payments.providers import registry
from apps.payments.providers.fake import FakeProvider

User = get_user_model()
URL = "/api/mpesa/stk/push/"


class STKPushTargetNumberTests(APITestCase):
    def setUp(self):
        registry.use_provider(FakeProvider())
        cache.clear()  # reset throttle history between tests
        self.user = User.objects.create(phone_number="254700000001")
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
        self.user = User.objects.create(phone_number="254700000002")
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
