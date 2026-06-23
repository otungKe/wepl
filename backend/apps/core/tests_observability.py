"""Observability tests (ADR-0020): structured logging context + health probes."""
import json
import logging

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.core import observability as obs
from apps.users.auth import STAGE_ACTIVE, STAGE_CLAIM

User = get_user_model()


class LogContextTests(TestCase):

    def tearDown(self):
        obs.clear()

    def test_context_filter_injects_bound_values(self):
        obs.bind(request_id="req-1", tenant_id=7, actor_id=42)
        record = logging.LogRecord("x", logging.INFO, __file__, 1, "msg", None, None)
        self.assertTrue(obs.ContextFilter().filter(record))
        self.assertEqual(record.request_id, "req-1")
        self.assertEqual(record.tenant_id, 7)
        self.assertEqual(record.actor_id, 42)

    def test_context_defaults_when_unbound(self):
        obs.clear()
        record = logging.LogRecord("x", logging.INFO, __file__, 1, "msg", None, None)
        obs.ContextFilter().filter(record)
        self.assertEqual(record.request_id, "")
        self.assertIsNone(record.tenant_id)
        self.assertIsNone(record.actor_id)

    def test_json_formatter_emits_valid_line_with_context(self):
        obs.bind(request_id="req-9", tenant_id=3, actor_id=5)
        record = logging.LogRecord("apps.demo", logging.WARNING, __file__, 10, "boom", None, None)
        obs.ContextFilter().filter(record)
        line = obs.JSONFormatter().format(record)
        doc = json.loads(line)
        self.assertEqual(doc["level"], "WARNING")
        self.assertEqual(doc["logger"], "apps.demo")
        self.assertEqual(doc["message"], "boom")
        self.assertEqual(doc["request_id"], "req-9")
        self.assertEqual(doc["tenant_id"], 3)
        self.assertEqual(doc["actor_id"], 5)

    def test_json_formatter_includes_exception(self):
        try:
            raise ValueError("kaboom")
        except ValueError:
            import sys
            record = logging.LogRecord("x", logging.ERROR, __file__, 1, "err", None, sys.exc_info())
        doc = json.loads(obs.JSONFormatter().format(record))
        self.assertIn("kaboom", doc["exc_info"])

    def test_clear_removes_context(self):
        obs.bind(request_id="r", actor_id=1)
        obs.clear()
        self.assertIsNone(obs.get("request_id"))
        self.assertIsNone(obs.get("actor_id"))


class AuthContextBindingTests(TestCase):
    """The JWT auth class binds actor_id (and tenant_id for members) into the
    log context, so lines emitted during dispatch carry them."""

    def tearDown(self):
        obs.clear()

    def _request_with_token(self, user):
        from rest_framework.test import APIRequestFactory
        token = AccessToken.for_user(user)
        token[STAGE_CLAIM] = STAGE_ACTIVE
        return APIRequestFactory().get(
            "/api/users/protected/", HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_member_auth_binds_actor_and_tenant(self):
        from apps.tenants.auth import TenantJWTAuthentication
        obs.clear()
        user = User.objects.create(phone_number="254700000001")
        TenantJWTAuthentication().authenticate(self._request_with_token(user))
        self.assertEqual(obs.get("actor_id"), user.id)
        self.assertIsNotNone(obs.get("tenant_id"))

    def test_staff_auth_binds_actor_but_not_tenant(self):
        from apps.tenants.auth import TenantJWTAuthentication
        obs.clear()
        staff = User.objects.create(phone_number="254700000002", is_staff=True)
        TenantJWTAuthentication().authenticate(self._request_with_token(staff))
        self.assertEqual(obs.get("actor_id"), staff.id)
        self.assertIsNone(obs.get("tenant_id"))  # operators aren't tenant-pinned


class HealthProbeTests(TestCase):

    def test_live_is_always_ok(self):
        r = self.client.get("/health/live/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ok")

    def test_ready_checks_dependencies(self):
        r = self.client.get("/health/ready/")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["db"], "ok")
        self.assertEqual(body["cache"], "ok")

    def test_legacy_health_alias(self):
        self.assertEqual(self.client.get("/health/").status_code, 200)
