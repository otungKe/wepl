"""Multi-channel routing + dead-letter tests (ADR-0015)."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from . import deadletter
from .channels import CHANNELS, InAppChannel, channels_for
from .models import (
    Notification, NotificationDeadLetter, NotificationPreferences,
)

User = get_user_model()


def make_user(phone="254700000001"):
    u = User.objects.create(phone_number=phone)
    u.set_pin("123456")
    return u


def prefs_for(user, **overrides):
    p, _ = NotificationPreferences.objects.get_or_create(user=user)
    for k, v in overrides.items():
        setattr(p, k, v)
    p.save()
    return p


class RoutingTests(TestCase):

    def setUp(self):
        self.user = make_user()

    def test_allowed_type_routes_to_inapp_and_push(self):
        p = prefs_for(self.user)
        self.assertEqual(channels_for("contribution_payment", p), ["in_app", "push"])

    def test_master_switch_suppresses_all(self):
        p = prefs_for(self.user, push_enabled=False)
        self.assertEqual(channels_for("contribution_payment", p), [])

    def test_disabled_category_suppresses_type(self):
        p = prefs_for(self.user, payments=False)
        self.assertEqual(channels_for("contribution_payment", p), [])  # payments type
        # a type in a different (enabled) category still routes
        self.assertEqual(channels_for("new_message", p), ["in_app", "push"])

    def test_unmapped_type_passes_through(self):
        p = prefs_for(self.user)
        self.assertEqual(channels_for("some_system_message", p), ["in_app", "push"])


class ChannelTests(TestCase):

    def setUp(self):
        self.user = make_user()

    def test_registry_has_inapp_and_push(self):
        self.assertIn("in_app", CHANNELS)
        self.assertIn("push", CHANNELS)

    def test_inapp_channel_creates_durable_row(self):
        InAppChannel().deliver({
            "user_id": self.user.id, "notification_type": "new_message",
            "title": "Hi", "message": "there",
        })
        n = Notification.objects.get(user=self.user)
        self.assertEqual(n.title, "Hi")
        self.assertEqual(n.notification_type, "new_message")

    def test_inapp_channel_is_idempotent_on_event_id(self):
        payload = {"user_id": self.user.id, "notification_type": "x",
                   "title": "t", "message": "m", "event_id": 999}
        InAppChannel().deliver(payload)
        InAppChannel().deliver(payload)  # redelivery
        self.assertEqual(Notification.objects.filter(event_id=999).count(), 1)


class DeadLetterTests(TestCase):

    def test_record_persists_failure(self):
        dl = deadletter.record(
            channel="push", user_id=7, notification_type="advance_sent",
            payload={"user_id": 7, "title": "t"}, error="boom",
        )
        self.assertIsNotNone(dl)
        row = NotificationDeadLetter.objects.get()
        self.assertEqual(row.channel, "push")
        self.assertEqual(row.user_id, 7)
        self.assertEqual(row.notification_type, "advance_sent")
        self.assertIn("boom", row.error)
        self.assertIsNone(row.resolved_at)

    def test_record_infers_from_payload(self):
        deadletter.record(
            channel="in_app",
            payload={"user_id": 3, "notification_type": "reminder"},
            error="db down",
        )
        row = NotificationDeadLetter.objects.get()
        self.assertEqual(row.user_id, 3)
        self.assertEqual(row.notification_type, "reminder")
