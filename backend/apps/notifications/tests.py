"""Notification tests — ownership isolation + core behaviours.

Notifications are a *per-user* resource: every query is scoped to the owner, so
authorization here is ownership, not roles (hence no policy resolver — see
ADR-0009). These tests lock in that isolation (the IDOR boundary) and the
service guarantees the rest of the platform depends on.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Notification, NotificationPreferences, UserDevice
from .services import NotificationService

User = get_user_model()


def make_user(phone):
    u = User.objects.create(phone_number=phone)
    u.set_pin("123456")
    return u


def client_for(user) -> APIClient:
    # Notification endpoints use IsAuthenticated, so a plain force_authenticate suffices.
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def notify(user, **kw):
    defaults = dict(notification_type="generic", title="t", message="m")
    defaults.update(kw)
    return NotificationService.create(user=user, **defaults)


class NotificationOwnershipApiTests(TestCase):
    """A user must never touch another user's notifications."""

    def setUp(self):
        self.alice = make_user("254700000001")
        self.bob   = make_user("254700000002")
        self.bob_note = notify(self.bob, title="Bob's secret")

    def test_list_returns_only_own_notifications(self):
        notify(self.alice, title="Alice's note")
        r = client_for(self.alice).get("/api/notifications/")
        self.assertEqual(r.status_code, 200)
        titles = {n["title"] for n in r.json()}
        self.assertIn("Alice's note", titles)
        self.assertNotIn("Bob's secret", titles)

    def test_cannot_mark_anothers_notification_read(self):
        r = client_for(self.alice).post(f"/api/notifications/{self.bob_note.id}/read/")
        self.assertEqual(r.status_code, 200)  # endpoint is a no-op filter, not a 404
        self.bob_note.refresh_from_db()
        self.assertFalse(self.bob_note.is_read)  # Bob's note untouched

    def test_cannot_delete_anothers_notification(self):
        r = client_for(self.alice).delete(f"/api/notifications/{self.bob_note.id}/delete/")
        self.assertEqual(r.status_code, 204)
        self.assertTrue(Notification.objects.filter(id=self.bob_note.id).exists())  # still there

    def test_delete_all_only_affects_own(self):
        notify(self.alice)
        notify(self.alice)
        client_for(self.alice).delete("/api/notifications/delete-all/")
        self.assertEqual(Notification.objects.filter(user=self.alice).count(), 0)
        self.assertEqual(Notification.objects.filter(user=self.bob).count(), 1)

    def test_unread_count_is_per_user(self):
        notify(self.alice)
        notify(self.alice)
        r = client_for(self.alice).get("/api/notifications/unread-count/")
        self.assertEqual(r.json()["unread_count"], 2)


class NotificationServiceTests(TestCase):

    def setUp(self):
        self.user = make_user("254700000001")

    def test_create_is_idempotent_on_event_id(self):
        # The outbox relay is at-least-once; redelivery must not duplicate.
        n1 = NotificationService.create(
            user=self.user, notification_type="t", title="x", message="y", event_id=42)
        n2 = NotificationService.create(
            user=self.user, notification_type="t", title="x", message="y", event_id=42)
        self.assertEqual(n1.id, n2.id)
        self.assertEqual(Notification.objects.filter(event_id=42).count(), 1)

    def test_create_accepts_user_id(self):
        n = NotificationService.create(
            user_id=self.user.id, notification_type="t", title="x", message="y")
        self.assertEqual(n.user_id, self.user.id)

    def test_mark_all_read(self):
        notify(self.user)
        notify(self.user)
        NotificationService.mark_all_read(self.user)
        self.assertEqual(Notification.objects.filter(user=self.user, is_read=False).count(), 0)

    def test_register_device_upserts_on_token(self):
        d1 = NotificationService.register_device(self.user, "tok-abc", "android")
        d2 = NotificationService.register_device(self.user, "tok-abc", "ios")  # same token
        self.assertEqual(d1.id, d2.id)
        self.assertEqual(UserDevice.objects.filter(fcm_token="tok-abc").count(), 1)
        d2.refresh_from_db()
        self.assertEqual(d2.platform, "ios")

    def test_unregister_device(self):
        NotificationService.register_device(self.user, "tok-xyz", "android")
        NotificationService.unregister_device(self.user, "tok-xyz")
        self.assertFalse(UserDevice.objects.filter(fcm_token="tok-xyz").exists())


class NotificationPreferencesApiTests(TestCase):

    def setUp(self):
        self.user = make_user("254700000001")

    def test_defaults_created_on_first_get(self):
        r = client_for(self.user).get("/api/notifications/preferences/")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(all(r.json().values()))  # all flags default True

    def test_patch_updates_flags(self):
        r = client_for(self.user).patch(
            "/api/notifications/preferences/", {"payments": False}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["payments"])
        self.assertFalse(NotificationPreferences.objects.get(user=self.user).payments)

    def test_patch_rejects_non_boolean(self):
        r = client_for(self.user).patch(
            "/api/notifications/preferences/", {"payments": "nope"}, format="json")
        self.assertEqual(r.status_code, 400)
