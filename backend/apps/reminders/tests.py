"""Reminders hardening tests: atomic claim (no double-fire), catch-up, lock."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.notifications.models import Notification

from .models import Reminder
from .tasks import _LOCK_KEY, fire_due_reminders

User = get_user_model()


def make_user(phone="254700000001"):
    u = User.objects.create(phone_number=phone)
    u.set_pin("123456")
    return u


def make_reminder(user, *, recurrence="none", fire_offset=timedelta(minutes=-1), **kw):
    when = timezone.now() + fire_offset
    return Reminder.objects.create(
        user=user, title=kw.pop("title", "Pay up"), recurrence=recurrence,
        scheduled_for=when, next_fire_at=when, **kw,
    )


class ClaimTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_claim_succeeds_once_then_fails(self):
        r = make_reminder(self.user, recurrence="daily")
        self.assertTrue(r.claim())          # first caller wins
        self.assertFalse(r.claim())         # stale next_fire_at → no double-fire

    def test_one_time_reminder_deactivates_on_claim(self):
        r = make_reminder(self.user, recurrence="none")
        self.assertTrue(r.claim())
        r.refresh_from_db()
        self.assertFalse(r.is_active)
        self.assertEqual(r.send_count, 1)

    def test_recurring_advances_to_future_skipping_missed(self):
        # 5 days overdue, daily → should land on the next fire strictly after now
        r = make_reminder(self.user, recurrence="daily", fire_offset=timedelta(days=-5))
        self.assertTrue(r.claim())
        r.refresh_from_db()
        self.assertTrue(r.is_active)
        self.assertGreater(r.next_fire_at, timezone.now())   # catch-up, no backlog
        self.assertEqual(r.send_count, 1)

    def test_concurrent_claims_yield_single_winner(self):
        r = make_reminder(self.user, recurrence="weekly")
        r2 = Reminder.objects.get(pk=r.pk)   # a second in-memory copy (simulates worker B)
        self.assertEqual([r.claim(), r2.claim()].count(True), 1)


class FireDueTaskTests(TestCase):
    def setUp(self):
        self.user = make_user()
        cache.delete(_LOCK_KEY)
        self.addCleanup(cache.delete, _LOCK_KEY)

    def test_fires_due_and_creates_notification(self):
        make_reminder(self.user, title="Due now")
        fired = fire_due_reminders.apply().get()
        self.assertEqual(fired, 1)
        self.assertEqual(
            Notification.objects.filter(user=self.user, notification_type="reminder").count(), 1)

    def test_future_reminder_not_fired(self):
        make_reminder(self.user, fire_offset=timedelta(hours=1))
        self.assertEqual(fire_due_reminders.apply().get(), 0)
        self.assertEqual(Notification.objects.filter(user=self.user).count(), 0)

    def test_already_claimed_reminder_not_double_fired(self):
        r = make_reminder(self.user, recurrence="daily")
        self.assertTrue(r.claim())                      # worker A already fired this occurrence
        fired = fire_due_reminders.apply().get()        # this tick must skip it
        self.assertEqual(fired, 0)

    def test_lock_prevents_overlapping_run(self):
        make_reminder(self.user, title="Due now")
        cache.add(_LOCK_KEY, "1", timeout=60)           # another tick holds the lock
        self.assertEqual(fire_due_reminders.apply().get(), 0)
        self.assertEqual(Notification.objects.filter(user=self.user).count(), 0)

    def test_lock_released_after_run(self):
        make_reminder(self.user, title="Due now")
        fire_due_reminders.apply().get()
        self.assertIsNone(cache.get(_LOCK_KEY))         # lock cleared in finally
