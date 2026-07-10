"""Fail-open throttles: a cache/Redis outage must degrade rate limiting, not 500
every endpoint (the throttle runs in APIView.initial(), before the view)."""
from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory

from apps.core.throttling import (
    ResilientAnonRateThrottle, ResilientScopedRateThrottle, ResilientUserRateThrottle,
)


class _FakeUser:
    pk = 1
    is_authenticated = True


class FailOpenThrottleTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    def _boom(self, throttle, request, view=None):
        """Assert the throttle allows the request even when its cache errors."""
        with patch.object(throttle, "cache") as cache:
            cache.get.side_effect = ConnectionError("max number of clients reached")
            self.assertTrue(throttle.allow_request(request, view))

    def test_user_throttle_fails_open(self):
        request = self.factory.get("/api/notifications/unread-count/")
        request.user = _FakeUser()
        self._boom(ResilientUserRateThrottle(), request)

    def test_anon_throttle_fails_open(self):
        request = self.factory.get("/api/auth/otp/")
        request.user = None
        self._boom(ResilientAnonRateThrottle(), request)

    def test_scoped_throttle_fails_open(self):
        request = self.factory.get("/api/communities/invite/")
        request.user = _FakeUser()
        throttle = ResilientScopedRateThrottle()

        class _View:
            throttle_scope = "invite_lookup"

        self._boom(throttle, request, _View())

    def test_still_limits_when_cache_healthy(self):
        # Sanity: with a working cache the throttle still enforces its limit — the
        # fail-open path is only reached on error, not always-allow.
        request = self.factory.get("/api/notifications/unread-count/")
        request.user = _FakeUser()
        throttle = ResilientUserRateThrottle()
        throttle.rate = "1/min"
        throttle.num_requests, throttle.duration = 1, 60
        with patch.object(throttle, "cache") as cache:
            store = {}
            cache.get.side_effect = lambda k, d=None: store.get(k, d)
            cache.set.side_effect = lambda k, v, t=None: store.__setitem__(k, v)
            self.assertTrue(throttle.allow_request(request, None))   # 1st: allowed
            self.assertFalse(throttle.allow_request(request, None))  # 2nd: limited
