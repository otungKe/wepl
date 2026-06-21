import os
import subprocess
import sys
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.users.auth import STAGE_ACTIVE, STAGE_CLAIM, issue_tokens
from apps.users.tasks import send_kyc_verification_email

# .../backend — the directory that contains the importable `config` package.
BACKEND_DIR = Path(__file__).resolve().parents[2]


def _boot_production(extra_env):
    """Run ``django.setup()`` under config.settings.production in a subprocess.

    Django settings are process-global and already loaded (dev settings) inside
    the test runner, so a fresh subprocess is the only way to assert how the
    production settings module behaves at import/boot time.
    """
    env = {
        "PATH": os.environ.get("PATH", ""),
        "DJANGO_SETTINGS_MODULE": "config.settings.production",
        "SECRET_KEY": "test-secret",
        "ALLOWED_HOSTS": "example.com",
        "DB_NAME": "wepl",
        "DB_USER": "wepl",
        "DB_PASSWORD": "x",
        "DB_HOST": "127.0.0.1",
        "DB_PORT": "5432",
        "REDIS_URL": "redis://127.0.0.1:6379/0",
        "REDIS_CACHE_URL": "redis://127.0.0.1:6379/0",
    }
    env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-c", "import django; django.setup()"],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
    )


class ProductionOtpBypassGuardTests(SimpleTestCase):
    """P0-01: the staging OTP bypass must never be active in production."""

    def test_production_boots_with_bypass_disabled(self):
        result = _boot_production({})
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_production_refuses_to_boot_with_bypass_enabled(self):
        result = _boot_production({"STAGING_OTP_BYPASS": "true"})
        self.assertNotEqual(
            result.returncode, 0,
            msg="production settings booted with STAGING_OTP_BYPASS enabled",
        )
        self.assertIn("STAGING_OTP_BYPASS", result.stderr)


class TokenRefreshEndpointTests(TestCase):
    """The mobile client depends on POST /api/users/token/refresh/ to renew its
    60-minute access token; without it, testers are logged out every hour."""

    URL = "/api/users/token/refresh/"

    def setUp(self):
        self.user = get_user_model().objects.create_user(phone_number="254700000001")
        self.tokens = issue_tokens(self.user, STAGE_ACTIVE)
        self.client = APIClient()

    def test_refresh_returns_new_access_token(self):
        resp = self.client.post(self.URL, {"refresh": self.tokens["refresh"]}, format="json")
        self.assertEqual(resp.status_code, 200, msg=resp.content)
        self.assertIn("access", resp.data)

    def test_refresh_preserves_stage_claim(self):
        resp = self.client.post(self.URL, {"refresh": self.tokens["refresh"]}, format="json")
        access = AccessToken(resp.data["access"])
        self.assertEqual(access[STAGE_CLAIM], STAGE_ACTIVE)

    def test_invalid_refresh_token_is_rejected(self):
        resp = self.client.post(self.URL, {"refresh": "not-a-real-token"}, format="json")
        self.assertEqual(resp.status_code, 401)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class KYCVerificationEmailTaskTests(TestCase):
    """The KYC email send runs in a Celery task so it never blocks the request."""

    def test_task_sends_email_with_verification_link(self):
        verify_url = "https://wepl-api.onrender.com/api/users/kyc/verify-email/?token=abc123"
        send_kyc_verification_email.apply(kwargs={
            "email": "tester@example.com",
            "given_names": "Tester",
            "verify_url": verify_url,
            "user_id": 1,
        })
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(msg.to, ["tester@example.com"])
        self.assertIn(verify_url, msg.body)

    @override_settings(
        BREVO_API_KEY="xkeysib-test",
        DEFAULT_FROM_EMAIL="Wepl App <sender@example.com>",
    )
    def test_task_uses_brevo_http_api_when_key_set(self):
        from unittest.mock import patch

        verify_url = "https://wepl-api.onrender.com/api/users/kyc/verify-email/?token=xyz"
        with patch("apps.users.tasks.requests.post") as post:
            post.return_value.raise_for_status.return_value = None
            send_kyc_verification_email.apply(kwargs={
                "email": "tester@example.com",
                "given_names": "Tester",
                "verify_url": verify_url,
                "user_id": 1,
            })

        # No SMTP used; the Brevo API was called with the verified sender + link.
        self.assertEqual(len(mail.outbox), 0)
        post.assert_called_once()
        _, kwargs = post.call_args
        self.assertEqual(kwargs["headers"]["api-key"], "xkeysib-test")
        self.assertEqual(kwargs["json"]["sender"]["email"], "sender@example.com")
        self.assertEqual(kwargs["json"]["to"], [{"email": "tester@example.com"}])
        self.assertIn(verify_url, kwargs["json"]["textContent"])


class KYCAdminDecisionTests(TestCase):
    """Approving/rejecting KYC must notify the applicant via the event bus."""

    def test_approval_emits_event(self):
        from types import SimpleNamespace
        from apps.core.models import OutboxEvent
        from apps.users.admin import _notify_kyc_decision

        _notify_kyc_decision(SimpleNamespace(status="approved", user_id=11, rejection_reason=""))
        self.assertTrue(
            OutboxEvent.objects.filter(event_type="kyc_approved", payload__user_id=11).exists()
        )

    def test_rejection_emits_event_with_reason(self):
        from types import SimpleNamespace
        from apps.core.models import OutboxEvent
        from apps.users.admin import _notify_kyc_decision

        _notify_kyc_decision(SimpleNamespace(status="rejected", user_id=12, rejection_reason="Blurry ID"))
        ev = OutboxEvent.objects.get(event_type="kyc_rejected", payload__user_id=12)
        self.assertIn("Blurry ID", ev.payload["message"])


class AdminDashboardTests(TestCase):
    """The custom admin index renders the platform overview."""

    def test_index_shows_overview(self):
        staff = get_user_model().objects.create_user(phone_number="254700000099")
        staff.is_staff = True
        staff.is_superuser = True
        staff.save()
        self.client.force_login(staff)
        resp = self.client.get("/admin/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Platform overview")
        self.assertContains(resp, "KYC pending review")


class EnsureSuperuserTests(TestCase):
    """ensure_superuser provisions the admin from env vars, non-interactively."""

    def test_creates_and_updates_superuser_from_env(self):
        from django.core.management import call_command
        from django.test import override_settings  # noqa: F401  (kept for parity)

        import os
        os.environ["ADMIN_PHONE"] = "254700000555"
        os.environ["ADMIN_PASSWORD"] = "first-pass"
        try:
            call_command("ensure_superuser")
            u = get_user_model().objects.get(phone_number="254700000555")
            self.assertTrue(u.is_superuser and u.is_staff and u.is_active)
            self.assertTrue(u.check_password("first-pass"))

            # Re-run rotates the password without creating a duplicate.
            os.environ["ADMIN_PASSWORD"] = "second-pass"
            call_command("ensure_superuser")
            self.assertEqual(get_user_model().objects.filter(phone_number="254700000555").count(), 1)
            u.refresh_from_db()
            self.assertTrue(u.check_password("second-pass"))
        finally:
            os.environ.pop("ADMIN_PHONE", None)
            os.environ.pop("ADMIN_PASSWORD", None)

    def test_skips_when_env_unset(self):
        from django.core.management import call_command
        call_command("ensure_superuser")  # no env → no-op, must not raise
        self.assertFalse(get_user_model().objects.filter(is_superuser=True).exists())


class SeedAdminRolesTests(TestCase):
    """The seed_admin_roles command provisions scoped staff groups."""

    def test_creates_roles_with_permissions(self):
        from django.contrib.auth.models import Group
        from django.core.management import call_command

        call_command("seed_admin_roles")
        for name in ["KYC Reviewers", "Support", "Finance & Compliance"]:
            group = Group.objects.get(name=name)
            self.assertTrue(group.permissions.exists(), f"{name} has no permissions")
