"""Tests for the transactional outbox (Phase 2, ADR-0006)."""
from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase, override_settings
from unittest.mock import patch

from apps.core.events import emit
from apps.core.models import OutboxEvent
from apps.core.tasks import process_outbox
from apps.notifications.models import Notification

User = get_user_model()


def _emit(**over):
    kwargs = dict(user_id=1, title="T", message="M")
    kwargs.update(over)
    emit("test_event", **kwargs)


class EmitDurabilityTests(TestCase):
    def test_emit_writes_pending_outbox_event_in_transaction(self):
        _emit(user_id=42, contribution_id=7)
        ev = OutboxEvent.objects.get()
        self.assertEqual(ev.status, OutboxEvent.Status.PENDING)
        self.assertEqual(ev.event_type, "test_event")
        self.assertEqual(ev.payload["user_id"], 42)
        self.assertEqual(ev.payload["contribution_id"], 7)

    def test_emit_is_rolled_back_with_its_transaction(self):
        with self.assertRaises(ValueError):
            with transaction.atomic():
                _emit()
                raise ValueError("boom")
        # The event row was discarded with the rolled-back transaction (no phantom).
        self.assertEqual(OutboxEvent.objects.count(), 0)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class RelayDeliveryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(phone_number="+254700000800")

    def test_relay_delivers_and_marks_processed(self):
        _emit(user_id=self.user.id)
        result = process_outbox()
        self.assertEqual(result["processed"], 1)
        ev = OutboxEvent.objects.get()
        self.assertEqual(ev.status, OutboxEvent.Status.PROCESSED)
        self.assertIsNotNone(ev.processed_at)
        # The consumer ran (eager) and created exactly one notification, tagged
        # with the outbox event id.
        notif = Notification.objects.get(user=self.user)
        self.assertEqual(notif.event_id, ev.id)

    def test_redelivery_is_idempotent(self):
        _emit(user_id=self.user.id)
        ev = OutboxEvent.objects.get()
        process_outbox()
        # Simulate at-least-once redelivery: reset the event to PENDING and re-run.
        OutboxEvent.objects.filter(pk=ev.pk).update(status=OutboxEvent.Status.PENDING)
        process_outbox()
        self.assertEqual(Notification.objects.filter(event_id=ev.id).count(), 1)

    def test_nothing_to_do_is_a_noop(self):
        self.assertEqual(process_outbox(), {"processed": 0, "dead": 0})


class RelayFailureTests(TestCase):
    def test_failure_dead_letters_after_max_attempts(self):
        _emit()
        ev = OutboxEvent.objects.get()
        with patch("apps.core.events.domain_event.send", side_effect=RuntimeError("downstream down")):
            for _ in range(5):
                process_outbox(max_attempts=5)
                ev.refresh_from_db()
                if ev.status == OutboxEvent.Status.DEAD:
                    break
        ev.refresh_from_db()
        self.assertEqual(ev.status, OutboxEvent.Status.DEAD)
        self.assertEqual(ev.attempts, 5)
        self.assertIn("downstream down", ev.last_error)
