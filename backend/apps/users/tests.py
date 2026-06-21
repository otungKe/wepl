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
