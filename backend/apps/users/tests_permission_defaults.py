"""Every API endpoint needs a completed login unless it says otherwise.

The login ladder issues an intermediate token after the SMS code and an
active one after the PIN (apps/users/auth.py). DRF's bare IsAuthenticated
accepts both, so a view that names it lets an SMS-code-only token back in.
IsActiveSession is the project default; this test fails the build if a view
opts back into bare IsAuthenticated.
"""
from django.test import SimpleTestCase
from django.urls import get_resolver
from rest_framework.permissions import IsAuthenticated

# Owned by the thread changing apps/contributions under ADR-0027; remove the
# entry when that view drops IsAuthenticated. This set may only shrink.
KNOWN_BARE_IS_AUTHENTICATED = {
    'apps.contributions.views.collect.STKPushView',
}


def _drf_views(patterns):
    for p in patterns:
        if hasattr(p, 'url_patterns'):
            yield from _drf_views(p.url_patterns)
            continue
        cls = getattr(p.callback, 'cls', None)
        if cls is not None and hasattr(cls, 'permission_classes'):
            yield cls


class PermissionDefaultTests(SimpleTestCase):
    def test_default_permission_is_active_session(self):
        from rest_framework.settings import api_settings
        from apps.users.auth import IsActiveSession
        self.assertEqual(list(api_settings.DEFAULT_PERMISSION_CLASSES), [IsActiveSession])

    def test_no_view_accepts_an_otp_stage_token_by_accident(self):
        offenders = {
            f'{cls.__module__}.{cls.__name__}'
            for cls in _drf_views(get_resolver().url_patterns)
            if IsAuthenticated in cls.permission_classes
        }
        self.assertEqual(offenders - KNOWN_BARE_IS_AUTHENTICATED, set())
        self.assertEqual(KNOWN_BARE_IS_AUTHENTICATED - offenders, set(),
                         'fixed — remove it from KNOWN_BARE_IS_AUTHENTICATED')


from django.contrib.auth import get_user_model  # noqa: E402
from django.test import TestCase  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402
from rest_framework_simplejwt.tokens import AccessToken  # noqa: E402

from apps.users.auth import STAGE_CLAIM, STAGE_OTP_RECOVERY, STAGE_OTP_VERIFIED  # noqa: E402


def _client(user, stage):
    token = AccessToken.for_user(user)
    token[STAGE_CLAIM] = stage
    client = APIClient()
    client.force_authenticate(user=user, token=token)
    return client


class OtpStageTokenTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create(phone_number="254711000001")
        self.user.set_pin("123456")
        self.user.save()

    def test_otp_stage_token_cannot_read_notifications(self):
        r = _client(self.user, STAGE_OTP_VERIFIED).get("/api/notifications/")
        self.assertEqual(r.status_code, 403)

    def test_otp_stage_token_cannot_delete_the_account(self):
        r = _client(self.user, STAGE_OTP_RECOVERY).delete("/api/users/account/")
        self.assertEqual(r.status_code, 403)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_suspended_member_cannot_reset_pin_into_a_session(self):
        from apps.controls.restrictions import RestrictionService
        RestrictionService.apply(self.user, "login", reason="fraud review")
        r = _client(self.user, STAGE_OTP_RECOVERY).post("/api/users/pin/reset/", {"pin": "654321"}, format="json")
        self.assertEqual(r.status_code, 403)
        self.assertNotIn("access", r.json())
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_pin("123456"))

    def test_unrestricted_member_can_still_reset_pin(self):
        r = _client(self.user, STAGE_OTP_RECOVERY).post("/api/users/pin/reset/", {"pin": "654321"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
