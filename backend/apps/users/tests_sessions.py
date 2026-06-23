"""Session registry & token-revocation tests (ADR-0010)."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from .auth import STAGE_ACTIVE, STAGE_CLAIM, issue_tokens
from .models import UserSession
from .sessions import SID_CLAIM

User = get_user_model()


def make_user(phone="254700000001"):
    u = User.objects.create(phone_number=phone)
    u.set_pin("123456")
    return u


def bearer(client, access):
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")


class IssueTokenSessionTests(TestCase):

    def test_active_login_creates_session_with_sid_claim(self):
        user = make_user()
        tokens = issue_tokens(user, STAGE_ACTIVE)
        self.assertEqual(UserSession.objects.filter(user=user).count(), 1)
        session = UserSession.objects.get(user=user)
        # the sid is embedded in both tokens
        refresh = RefreshToken(tokens["refresh"])
        self.assertEqual(refresh[SID_CLAIM], str(session.sid))

    def test_intermediate_stage_tokens_have_no_session(self):
        user = make_user()
        issue_tokens(user, "otp_verified")
        self.assertEqual(UserSession.objects.filter(user=user).count(), 0)

    def test_sid_survives_refresh_rotation(self):
        user = make_user()
        tokens = issue_tokens(user, STAGE_ACTIVE)
        sid = RefreshToken(tokens["refresh"])[SID_CLAIM]
        r = APIClient().post("/api/users/token/refresh/", {"refresh": tokens["refresh"]}, format="json")
        self.assertEqual(r.status_code, 200)
        # rotation returns a new refresh token that still carries the same sid
        new_refresh = RefreshToken(r.json()["refresh"])
        self.assertEqual(new_refresh[SID_CLAIM], sid)


class RevocationTests(TestCase):

    def setUp(self):
        self.user = make_user()
        self.tokens = issue_tokens(self.user, STAGE_ACTIVE)
        self.session = UserSession.objects.get(user=self.user)

    def test_access_token_rejected_after_session_revoked(self):
        client = APIClient()
        bearer(client, self.tokens["access"])
        # works before revocation
        self.assertEqual(client.get("/api/users/protected/").status_code, 200)
        # revoke
        self.session.revoked_at = timezone.now()
        self.session.save(update_fields=["revoked_at"])
        # the same access token is now rejected even though it hasn't expired
        self.assertEqual(client.get("/api/users/protected/").status_code, 401)

    def test_refresh_rejected_after_session_revoked(self):
        self.session.revoked_at = timezone.now()
        self.session.save(update_fields=["revoked_at"])
        r = APIClient().post("/api/users/token/refresh/", {"refresh": self.tokens["refresh"]}, format="json")
        self.assertEqual(r.status_code, 401)


class LogoutApiTests(TestCase):

    def setUp(self):
        self.user = make_user()
        self.tokens = issue_tokens(self.user, STAGE_ACTIVE)

    def test_logout_revokes_current_session(self):
        client = APIClient()
        bearer(client, self.tokens["access"])
        r = client.post("/api/users/logout/", {"refresh": self.tokens["refresh"]}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(UserSession.objects.get(user=self.user).is_active)
        # access token no longer works
        self.assertEqual(client.get("/api/users/protected/").status_code, 401)

    def test_logout_is_idempotent_without_refresh_body(self):
        client = APIClient()
        bearer(client, self.tokens["access"])
        r = client.post("/api/users/logout/", {}, format="json")
        self.assertEqual(r.status_code, 200)


class SessionListAndRevokeApiTests(TestCase):

    def setUp(self):
        self.user = make_user()
        # two logins → two sessions
        self.t1 = issue_tokens(self.user, STAGE_ACTIVE)
        self.t2 = issue_tokens(self.user, STAGE_ACTIVE)

    def _client(self, access):
        c = APIClient()
        bearer(c, access)
        return c

    def test_list_shows_active_sessions_and_flags_current(self):
        r = self._client(self.t1["access"]).get("/api/users/sessions/")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(len(body), 2)
        current = [s for s in body if s["is_current"]]
        self.assertEqual(len(current), 1)
        sid1 = str(RefreshToken(self.t1["refresh"])[SID_CLAIM])
        self.assertEqual(current[0]["sid"], sid1)

    def test_cannot_list_or_revoke_another_users_sessions(self):
        other = make_user("254700000002")
        other_tokens = issue_tokens(other, STAGE_ACTIVE)
        other_sid = RefreshToken(other_tokens["refresh"])[SID_CLAIM]
        # user tries to revoke other's session → 404 (scoped to own)
        r = self._client(self.t1["access"]).post(f"/api/users/sessions/{other_sid}/revoke/")
        self.assertEqual(r.status_code, 404)
        self.assertTrue(UserSession.objects.get(sid=other_sid).is_active)

    def test_revoke_specific_session(self):
        sid2 = str(RefreshToken(self.t2["refresh"])[SID_CLAIM])
        r = self._client(self.t1["access"]).post(f"/api/users/sessions/{sid2}/revoke/")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(UserSession.objects.get(sid=sid2).is_active)
        # session 1 still active
        self.assertEqual(UserSession.objects.filter(user=self.user, revoked_at__isnull=True).count(), 1)

    def test_revoke_others_keeps_current(self):
        r = self._client(self.t1["access"]).post("/api/users/sessions/revoke-others/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["revoked"], 1)
        active = UserSession.objects.filter(user=self.user, revoked_at__isnull=True)
        self.assertEqual(active.count(), 1)
        sid1 = str(RefreshToken(self.t1["refresh"])[SID_CLAIM])
        self.assertEqual(str(active.first().sid), sid1)
