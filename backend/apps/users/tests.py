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
    """The themed (django-unfold) admin renders with WEPL branding + sidebar."""

    def setUp(self):
        staff = get_user_model().objects.create_user(phone_number="254700000099")
        staff.is_staff = True
        staff.is_superuser = True
        staff.save()
        self.client.force_login(staff)

    def test_index_renders_with_branding_and_nav(self):
        resp = self.client.get("/admin/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "WEPL Platform Admin")   # Unfold SITE_HEADER
        self.assertContains(resp, "KYC profiles")          # sidebar navigation item

    def test_key_changelists_and_forms_render(self):
        for url in [
            "/admin/users/user/",
            "/admin/users/kycprofile/",
            "/admin/users/user/add/",
        ]:
            self.assertEqual(self.client.get(url).status_code, 200, url)


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


class PhoneNormalizationTests(SimpleTestCase):
    """normalize_phone collapses every Kenyan MSISDN shape to 2547XXXXXXXX."""

    def test_shapes(self):
        from apps.users.phone import normalize_phone
        cases = {
            "0712345678":     "254712345678",
            "712345678":      "254712345678",
            "+254712345678":  "254712345678",
            "254712345678":   "254712345678",
            "254 712 345 678": "254712345678",
            "0110123456":     "254110123456",
            "":               "",
            None:             "",
        }
        for raw, expected in cases.items():
            self.assertEqual(normalize_phone(raw), expected, f"{raw!r}")


class CrossFormatLoginTests(TestCase):
    """An account is reachable from any client regardless of the phone shape
    the caller types — the regression behind 'correct phone & PIN rejected'."""

    def setUp(self):
        self.client = APIClient()
        # New registrations (and the 0011 backfill) store the canonical shape.
        self.user = get_user_model().objects.create(phone_number="254712345678")
        self.user.set_pin("123456")

    def test_login_with_local_format(self):
        # User types 0712… on one client — must still resolve to the canonical row.
        r = self.client.post("/api/users/pin/login/",
                             {"phone_number": "0712345678", "pin": "123456"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)

    def test_login_with_international_format(self):
        r = self.client.post("/api/users/pin/login/",
                             {"phone_number": "254712345678", "pin": "123456"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)

    def test_login_with_plus_format(self):
        r = self.client.post("/api/users/pin/login/",
                             {"phone_number": "+254 712 345 678", "pin": "123456"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)


class VerificationRequestTests(TestCase):
    """Verification Center's ongoing requests: a user sees only their own,
    and can answer an open request (note and/or document) once."""

    def setUp(self):
        self.user  = get_user_model().objects.create_user(phone_number="254700000201")
        self.other = get_user_model().objects.create_user(phone_number="254700000202")
        tokens = issue_tokens(self.user, STAGE_ACTIVE)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

    def _make(self, user, **kw):
        from apps.users.models import VerificationRequest
        return VerificationRequest.objects.create(
            user=user, title=kw.pop("title", "Proof of address"),
            detail=kw.pop("detail", "Please upload a utility bill."), **kw)

    def test_list_returns_only_my_requests(self):
        self._make(self.user, kind="address_proof")
        self._make(self.other, title="Someone else")
        r = self.client.get("/api/users/verification-requests/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data), 1)
        self.assertEqual(r.data[0]["title"], "Proof of address")
        self.assertEqual(r.data[0]["status"], "open")

    def test_respond_moves_to_submitted(self):
        req = self._make(self.user)
        r = self.client.post(f"/api/users/verification-requests/{req.id}/respond/",
                             {"response_note": "Here it is"}, format="json")
        self.assertEqual(r.status_code, 200, msg=r.content)
        req.refresh_from_db()
        self.assertEqual(req.status, "submitted")
        self.assertIsNotNone(req.responded_at)

    def test_respond_requires_a_note_or_document(self):
        req = self._make(self.user)
        r = self.client.post(f"/api/users/verification-requests/{req.id}/respond/", {}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_cannot_respond_twice(self):
        req = self._make(self.user, status="submitted")
        r = self.client.post(f"/api/users/verification-requests/{req.id}/respond/",
                             {"response_note": "again"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_cannot_respond_to_another_users_request(self):
        req = self._make(self.other)
        r = self.client.post(f"/api/users/verification-requests/{req.id}/respond/",
                             {"response_note": "x"}, format="json")
        self.assertEqual(r.status_code, 404)


class PaymentMethodTests(TestCase):
    """Scalable payment methods: M-Pesa is live; card/bank return coming-soon."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(phone_number="254700000301")
        tokens = issue_tokens(self.user, STAGE_ACTIVE)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

    def test_link_mpesa_first_is_default(self):
        r = self.client.post("/api/users/payment-methods/",
                             {"kind": "mpesa", "mpesa_phone": "0712345678"}, format="json")
        self.assertEqual(r.status_code, 201, msg=r.content)
        self.assertTrue(r.data["is_default"])
        self.assertEqual(r.data["mpesa_phone"], "254712345678")  # normalised

    def test_invalid_mpesa_rejected(self):
        r = self.client.post("/api/users/payment-methods/",
                             {"kind": "mpesa", "mpesa_phone": "12345"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_duplicate_mpesa_rejected(self):
        self.client.post("/api/users/payment-methods/", {"kind": "mpesa", "mpesa_phone": "0712345678"}, format="json")
        r = self.client.post("/api/users/payment-methods/", {"kind": "mpesa", "mpesa_phone": "0712345678"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_card_and_bank_are_coming_soon(self):
        for kind in ("card", "bank"):
            r = self.client.post("/api/users/payment-methods/", {"kind": kind}, format="json")
            self.assertEqual(r.status_code, 501, msg=kind)
            self.assertEqual(r.data.get("code"), "RAIL_UNAVAILABLE")

    def test_set_default_moves_flag(self):
        a = self.client.post("/api/users/payment-methods/", {"kind": "mpesa", "mpesa_phone": "0712345678"}, format="json").data
        b = self.client.post("/api/users/payment-methods/", {"kind": "mpesa", "mpesa_phone": "0722333444"}, format="json").data
        r = self.client.post(f"/api/users/payment-methods/{b['id']}/default/")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["is_default"])
        # a is no longer default
        methods = {m["id"]: m for m in self.client.get("/api/users/payment-methods/").data}
        self.assertFalse(methods[a["id"]]["is_default"])

    def test_delete_promotes_another_to_default(self):
        a = self.client.post("/api/users/payment-methods/", {"kind": "mpesa", "mpesa_phone": "0712345678"}, format="json").data
        b = self.client.post("/api/users/payment-methods/", {"kind": "mpesa", "mpesa_phone": "0722333444"}, format="json").data
        # a is default (first); delete it → b becomes default
        r = self.client.delete(f"/api/users/payment-methods/{a['id']}/")
        self.assertEqual(r.status_code, 204)
        methods = self.client.get("/api/users/payment-methods/").data
        self.assertEqual(len(methods), 1)
        self.assertTrue(methods[0]["is_default"])

    def test_only_owner_sees_methods(self):
        self.client.post("/api/users/payment-methods/", {"kind": "mpesa", "mpesa_phone": "0712345678"}, format="json")
        other = get_user_model().objects.create_user(phone_number="254700000302")
        tok = issue_tokens(other, STAGE_ACTIVE)
        c2 = APIClient(); c2.credentials(HTTP_AUTHORIZATION=f"Bearer {tok['access']}")
        self.assertEqual(len(c2.get("/api/users/payment-methods/").data), 0)


class SecurityAlertsTests(TestCase):
    """Security & sign-in alerts fire on a PIN change and a new-device sign-in,
    and the security notification category is mandatory (can't be disabled)."""

    def test_pin_change_alerts_but_first_set_does_not(self):
        from apps.users.services import PINService
        from apps.core.models import OutboxEvent
        user = get_user_model().objects.create_user(phone_number="254700000401")
        PINService.set_pin(user, "123456")  # first-ever set — no alert
        self.assertFalse(OutboxEvent.objects.filter(event_type="security_pin_changed").exists())
        PINService.set_pin(user, "654321")  # change — alert
        self.assertTrue(OutboxEvent.objects.filter(
            event_type="security_pin_changed", payload__user_id=user.id).exists())

    def test_new_device_signin_alerts_once(self):
        from types import SimpleNamespace
        from apps.users.sessions import create_session
        from apps.core.models import OutboxEvent
        user = get_user_model().objects.create_user(phone_number="254700000402")
        req = SimpleNamespace(META={"HTTP_USER_AGENT": "Wepl/1.0 (iPhone; iOS 17)", "REMOTE_ADDR": "1.2.3.4"})
        create_session(user, req)
        create_session(user, req)  # same device — no second alert
        self.assertEqual(OutboxEvent.objects.filter(
            event_type="security_new_signin", payload__user_id=user.id).count(), 1)

    def test_security_pref_is_returned_and_not_disableable(self):
        user = get_user_model().objects.create_user(phone_number="254700000403")
        tokens = issue_tokens(user, STAGE_ACTIVE)
        c = APIClient(); c.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        r = c.get("/api/notifications/preferences/")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["security"])
        # Attempting to turn it off is ignored — it stays on.
        r2 = c.patch("/api/notifications/preferences/", {"security": False}, format="json")
        self.assertTrue(r2.data["security"])


class DataExportTests(TestCase):
    """Self-serve export returns the user's own data, scoped to them."""

    def test_export_returns_scoped_sections(self):
        user = get_user_model().objects.create_user(phone_number="254700000501")
        tokens = issue_tokens(user, STAGE_ACTIVE)
        c = APIClient(); c.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        r = c.get("/api/users/data-export/")
        self.assertEqual(r.status_code, 200, msg=r.content)
        body = r.json()
        self.assertEqual(body["account"]["phone_number"], "254700000501")
        for key in ("account", "identity_verification", "privacy_preferences",
                    "communities", "contributions", "transactions",
                    "payment_methods", "exported_at"):
            self.assertIn(key, body)
