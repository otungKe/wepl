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


class IdentityProviderPortTests(TestCase):
    """The IdentityVerificationProvider port and its adapters (apps.users.identity)."""

    def _subject(self):
        from apps.users.identity import IdentitySubject
        return IdentitySubject(
            id_number="12345678", given_names="Jane", surname="Doe",
            date_of_birth="1990-01-01",
        )

    def test_manual_provider_routes_to_review(self):
        from apps.users.identity import MANUAL_REVIEW
        from apps.users.identity.manual import ManualProvider
        r = ManualProvider().verify_identity(self._subject())
        self.assertEqual(r.state, MANUAL_REVIEW)
        self.assertEqual(r.provider, "manual")
        self.assertTrue(r.is_terminal)

    def test_fake_provider_verifies_by_default(self):
        from apps.users.identity import VERIFIED
        from apps.users.identity.fake import FakeProvider
        r = FakeProvider().verify_identity(self._subject())
        self.assertEqual(r.state, VERIFIED)
        self.assertEqual(r.provider, "fake")

    def test_fake_provider_can_reject(self):
        from apps.users.identity import REJECTED
        from apps.users.identity.fake import FakeProvider
        r = FakeProvider(outcome=REJECTED).verify_identity(self._subject())
        self.assertEqual(r.state, REJECTED)

    def test_registry_override_wins(self):
        from apps.users.identity.manual import ManualProvider
        from apps.users.identity.registry import get_provider, use_provider
        try:
            use_provider(ManualProvider())
            self.assertEqual(get_provider().name, "manual")
        finally:
            use_provider(None)


class IdentityCheckApplyTests(TestCase):
    """`_run_identity_check` applies the provider outcome to the KYC row and
    notifies the applicant on a terminal decision."""

    def _make_kyc(self, phone):
        from datetime import date
        from apps.users.models import KYCProfile
        user = get_user_model().objects.create_user(phone_number=phone)
        kyc = KYCProfile.objects.create(
            user=user, given_names="Jane", surname="Doe", id_number=f"ID{user.pk}",
            date_of_birth=date(1990, 1, 1), email="j@example.com", status="pending",
        )
        return user, kyc

    def test_verified_approves_and_notifies(self):
        from apps.core.models import OutboxEvent
        from apps.users.identity.fake import FakeProvider
        from apps.users.identity.registry import use_provider
        from apps.users.views.kyc import _run_identity_check
        user, kyc = self._make_kyc("254700000701")
        try:
            use_provider(FakeProvider())   # VERIFIED
            _run_identity_check(kyc)
        finally:
            use_provider(None)
        kyc.refresh_from_db()
        self.assertEqual(kyc.status, "approved")
        self.assertEqual(kyc.verification_provider, "fake")
        self.assertEqual(kyc.verification_state, "verified")
        self.assertIsNotNone(kyc.verification_checked_at)
        self.assertTrue(OutboxEvent.objects.filter(
            event_type="kyc_approved", payload__user_id=user.id).exists())

    def test_manual_leaves_pending_without_terminal_notification(self):
        from apps.core.models import OutboxEvent
        from apps.users.identity.manual import ManualProvider
        from apps.users.identity.registry import use_provider
        from apps.users.views.kyc import _run_identity_check
        user, kyc = self._make_kyc("254700000702")
        try:
            use_provider(ManualProvider())
            _run_identity_check(kyc)
        finally:
            use_provider(None)
        kyc.refresh_from_db()
        self.assertEqual(kyc.status, "pending")
        self.assertEqual(kyc.verification_state, "manual_review")
        self.assertFalse(OutboxEvent.objects.filter(
            event_type="kyc_approved", payload__user_id=user.id).exists())

    def test_rejected_sets_reason_and_notifies(self):
        from apps.core.models import OutboxEvent
        from apps.users.identity import REJECTED
        from apps.users.identity.fake import FakeProvider
        from apps.users.identity.registry import use_provider
        from apps.users.views.kyc import _run_identity_check
        user, kyc = self._make_kyc("254700000703")
        try:
            use_provider(FakeProvider(outcome=REJECTED, reason="Face did not match ID."))
            _run_identity_check(kyc)
        finally:
            use_provider(None)
        kyc.refresh_from_db()
        self.assertEqual(kyc.status, "rejected")
        self.assertEqual(kyc.rejection_reason, "Face did not match ID.")
        self.assertTrue(OutboxEvent.objects.filter(
            event_type="kyc_rejected", payload__user_id=user.id).exists())


_SAMPLE_ID_TEXT = """
JAMHURI YA KENYA
REPUBLIC OF KENYA
SERIAL NUMBER 123456
ID NUMBER 12345678
FULL NAMES JANE DOE
DATE OF BIRTH 01.01.1990
SEX FEMALE
DISTRICT OF BIRTH NAIROBI
"""


class KenyanIdParserTests(SimpleTestCase):
    """Pure text parser/detector — no OCR binary needed."""

    def test_detects_and_extracts_fields(self):
        from apps.users.ocr.kenyan_id import parse_kenyan_id
        scan = parse_kenyan_id(_SAMPLE_ID_TEXT)
        self.assertTrue(scan.is_kenyan_id)
        self.assertGreaterEqual(scan.marker_hits, 2)
        self.assertEqual(scan.id_number, "12345678")
        self.assertEqual(scan.date_of_birth, "1990-01-01")

    def test_non_id_text_not_detected(self):
        from apps.users.ocr.kenyan_id import parse_kenyan_id
        scan = parse_kenyan_id("Grocery receipt total 450 thank you")
        self.assertFalse(scan.is_kenyan_id)

    def test_cross_check_flags_matches_and_mismatch(self):
        from apps.users.ocr.kenyan_id import cross_check, parse_kenyan_id
        scan = parse_kenyan_id(_SAMPLE_ID_TEXT)
        ok = cross_check(scan, id_number="12345678", date_of_birth="1990-01-01")
        self.assertTrue(ok["id_number_match"])
        self.assertTrue(ok["dob_match"])
        self.assertFalse(ok["mismatch"])
        bad = cross_check(scan, id_number="99999999", date_of_birth="1990-01-01")
        self.assertFalse(bad["id_number_match"])
        self.assertTrue(bad["mismatch"])


class OcrEngineTests(TestCase):
    def test_run_id_ocr_with_fake_engine(self):
        from apps.users.ocr import run_id_ocr
        from apps.users.ocr.engine import FakeOcrEngine, use_engine
        try:
            use_engine(FakeOcrEngine(_SAMPLE_ID_TEXT))
            r = run_id_ocr(b"fake-bytes", id_number="12345678", date_of_birth="1990-01-01")
        finally:
            use_engine(None)
        self.assertTrue(r["detected"])
        self.assertTrue(r["id_number_match"])
        self.assertEqual(r["engine"], "fake")

    def test_empty_image_degrades(self):
        from apps.users.ocr import run_id_ocr
        r = run_id_ocr(b"")
        self.assertFalse(r["detected"])

    def test_null_engine_when_no_backend(self):
        from apps.users.ocr import run_id_ocr
        from apps.users.ocr.engine import NullOcrEngine, use_engine
        try:
            use_engine(NullOcrEngine())
            r = run_id_ocr(b"fake-bytes", id_number="12345678")
        finally:
            use_engine(None)
        self.assertFalse(r["detected"])   # no text → not an ID, manual review


class IdentityCheckOcrIntegrationTests(TestCase):
    """The identity check attaches the OCR cross-check to verification_detail."""

    def test_ocr_detail_recorded(self):
        from datetime import date
        from django.core.files.uploadedfile import SimpleUploadedFile
        from apps.users.models import KYCProfile
        from apps.users.identity.manual import ManualProvider
        from apps.users.identity.registry import use_provider
        from apps.users.ocr.engine import FakeOcrEngine, use_engine
        from apps.users.views.kyc import _run_identity_check

        user = get_user_model().objects.create_user(phone_number="254700000801")
        kyc = KYCProfile.objects.create(
            user=user, given_names="Jane", surname="Doe", id_number="12345678",
            date_of_birth=date(1990, 1, 1), email="j@example.com", status="pending",
            id_front=SimpleUploadedFile("id.jpg", b"\xff\xd8fake", content_type="image/jpeg"),
        )
        try:
            use_provider(ManualProvider())
            use_engine(FakeOcrEngine(_SAMPLE_ID_TEXT))
            _run_identity_check(kyc)
        finally:
            use_provider(None)
            use_engine(None)
        kyc.refresh_from_db()
        ocr = kyc.verification_detail.get("ocr")
        self.assertIsNotNone(ocr)
        self.assertTrue(ocr["detected"])
        self.assertTrue(ocr["id_number_match"])
        self.assertFalse(ocr["mismatch"])


class KYCMandatoryDocsTests(TestCase):
    """Both ID sides and a selfie are required on submission."""

    def _base_payload(self):
        return {
            "given_names": "Jane", "surname": "Doe", "id_number": "12345678",
            "kra_pin": "A012345678Z",
            "date_of_birth": "1990-01-01", "email": "j@example.com",
            "physical_address": "123 Riverside", "county": "Nairobi",
            "occupation": "Engineer", "source_of_income": "employment",
            "expected_monthly_income": "under_250k",
        }

    def test_kra_pin_required_and_format_checked(self):
        from apps.users.serializers import KYCSubmitSerializer
        # Missing
        p = self._base_payload(); p.pop("kra_pin")
        s = KYCSubmitSerializer(data=p)
        self.assertFalse(s.is_valid())
        self.assertIn("kra_pin", s.errors)
        # Bad format
        p = self._base_payload(); p["kra_pin"] = "12345"
        s = KYCSubmitSerializer(data=p)
        self.assertFalse(s.is_valid())
        self.assertIn("kra_pin", s.errors)

    def test_documents_are_required(self):
        from apps.users.serializers import KYCSubmitSerializer
        s = KYCSubmitSerializer(data=self._base_payload())
        self.assertFalse(s.is_valid())
        for field in ("id_front", "id_back", "selfie"):
            self.assertIn(field, s.errors)

    def test_valid_with_all_documents(self):
        from io import BytesIO
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile
        from apps.users.serializers import KYCSubmitSerializer

        def img(n):
            buf = BytesIO()
            Image.new("RGB", (8, 8), "white").save(buf, "JPEG")
            return SimpleUploadedFile(n, buf.getvalue(), content_type="image/jpeg")

        s = KYCSubmitSerializer(data={
            **self._base_payload(),
            "id_front": img("f.jpg"), "id_back": img("b.jpg"), "selfie": img("s.jpg"),
        })
        self.assertTrue(s.is_valid(), msg=s.errors)


class KYCAdminRenderTests(TestCase):
    """Guards the admin KYC change-page renderer (verification_summary) against
    the Django-6 format_html 'args required' regression that 500'd the page."""

    def _summary(self, obj):
        from django.contrib.admin.sites import site
        from apps.users.admin import KYCProfileAdmin
        from apps.users.models import KYCProfile
        return KYCProfileAdmin(KYCProfile, site).verification_summary(obj)

    def test_renders_for_all_detail_shapes(self):
        from django.utils import timezone
        from apps.users.models import KYCProfile
        # OCR present with a mismatch
        self.assertIn("MISMATCH", self._summary(KYCProfile(
            verification_provider="manual", verification_state="manual_review",
            verification_checked_at=timezone.now(),
            verification_detail={"ocr": {"detected": True, "id_number_read": "12345678",
                                         "id_number_match": False, "dob_read": "1990-01-01",
                                         "dob_match": True, "engine": "tesseract"}},
        )))
        # Empty row (older submission) — must not raise
        self.assertIn("No OCR result", self._summary(KYCProfile()))
        # Detail present but no ocr key — must not raise
        self.assertTrue(self._summary(KYCProfile(verification_detail={"x": "y"})))
        # detected False + unread fields
        self.assertTrue(self._summary(KYCProfile(
            verification_detail={"ocr": {"detected": False, "id_number_match": None, "dob_match": None}})))

    def test_change_page_renders_end_to_end(self):
        from datetime import date
        from django.utils import timezone
        from apps.users.models import KYCProfile
        staff = get_user_model().objects.create_user(phone_number="254700000909")
        staff.is_staff = staff.is_superuser = True
        staff.save()
        applicant = get_user_model().objects.create_user(phone_number="254700000910")
        kyc = KYCProfile.objects.create(
            user=applicant, given_names="Jane", surname="Doe", id_number="12345678",
            kra_pin="A012345678Z", date_of_birth=date(1990, 1, 1), status="pending",
            verification_provider="manual", verification_state="manual_review",
            verification_checked_at=timezone.now(),
            verification_detail={"ocr": {"detected": True, "id_number_read": "12345678",
                                         "id_number_match": False, "dob_read": None,
                                         "dob_match": None, "engine": "tesseract"}},
        )
        self.client.force_login(staff)
        resp = self.client.get(f"/admin/users/kycprofile/{kyc.id}/change/")
        self.assertEqual(resp.status_code, 200, msg=resp.content[:300])
