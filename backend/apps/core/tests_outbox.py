"""Tests for the transactional outbox (Phase 2, ADR-0006)."""
from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase, override_settings
from unittest.mock import patch

from apps.core.events import (
    emit, register_inline_consumer, _INLINE_CONSUMERS,
)
from apps.core.models import OutboxDelivery, OutboxEvent
from apps.core.tasks import process_inline_deliveries, process_outbox
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


class EnvelopeTests(TestCase):
    """The ADR-0029 envelope wraps the body without disturbing existing callers."""

    def test_notification_callers_get_blank_envelope_defaults(self):
        # An existing-shape emit() (no envelope kwargs) stores blank keys, a
        # populated occurred_at, and schema_version 1 — zero behaviour change.
        _emit(user_id=42)
        ev = OutboxEvent.objects.get()
        self.assertEqual(ev.aggregate_key, "")
        self.assertEqual(ev.dedup_key, "")
        self.assertEqual(ev.schema_version, 1)
        self.assertIsNotNone(ev.occurred_at)
        # The body is unchanged — still the notification fields.
        self.assertEqual(ev.payload["user_id"], 42)

    def test_envelope_fields_are_stored_when_provided(self):
        _emit(aggregate_key="payment:123", dedup_key="payment.settled:ft=123",
              schema_version=2)
        ev = OutboxEvent.objects.get()
        self.assertEqual(ev.aggregate_key, "payment:123")
        self.assertEqual(ev.dedup_key, "payment.settled:ft=123")
        self.assertEqual(ev.schema_version, 2)


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


class InlineDeliveryTests(TestCase):
    """The ADR-0029 Stage 2 inline_atomic lane: per-consumer delivery rows,
    delivered independently of the notification (enqueue) lane."""

    def setUp(self):
        # A fake idempotent inline consumer on a dedicated event type. Registered
        # per-test and torn down so the module-global registry never leaks.
        self.calls = []
        register_inline_consumer(
            "test.inline", {"inline_event"},
            lambda event: self.calls.append(event.id),
        )
        self.addCleanup(lambda: _INLINE_CONSUMERS.pop("test.inline", None))

    def _emit_inline(self, **over):
        kwargs = dict(user_id=1, title="T", message="M", dedup_key="dk-1")
        kwargs.update(over)
        emit("inline_event", **kwargs)

    def test_emit_fans_out_a_delivery_row_per_inline_consumer(self):
        self._emit_inline()
        ev = OutboxEvent.objects.get()
        d = OutboxDelivery.objects.get()
        self.assertEqual(d.outbox_event_id, ev.id)
        self.assertEqual(d.consumer_name, "test.inline")
        self.assertEqual(d.status, OutboxDelivery.Status.PENDING)

    def test_non_matching_event_type_creates_no_delivery(self):
        # A different event type has no inline subscriber → no delivery rows
        # (and the notification lane is unaffected).
        emit("some_other_event", user_id=1, title="T", message="M")
        self.assertEqual(OutboxDelivery.objects.count(), 0)

    def test_relay_runs_handler_and_marks_processed(self):
        self._emit_inline()
        result = process_inline_deliveries()
        self.assertEqual(result, {"processed": 1, "dead": 0})
        d = OutboxDelivery.objects.get()
        self.assertEqual(d.status, OutboxDelivery.Status.PROCESSED)
        self.assertIsNotNone(d.processed_at)
        self.assertEqual(len(self.calls), 1)

    def test_redelivery_reruns_the_idempotent_handler(self):
        self._emit_inline()
        process_inline_deliveries()
        d = OutboxDelivery.objects.get()
        # Simulate at-least-once redelivery.
        OutboxDelivery.objects.filter(pk=d.pk).update(status=OutboxDelivery.Status.PENDING)
        process_inline_deliveries()
        d.refresh_from_db()
        self.assertEqual(d.status, OutboxDelivery.Status.PROCESSED)
        # The handler ran again (delivery is at-least-once); real consumers dedupe
        # on their idempotency key (post_journal), so the *effect* is once.
        self.assertEqual(len(self.calls), 2)

    def test_failing_handler_dead_letters_after_max_attempts(self):
        _INLINE_CONSUMERS.pop("test.inline", None)
        register_inline_consumer(
            "test.inline", {"inline_event"},
            lambda event: (_ for _ in ()).throw(RuntimeError("consumer boom")),
        )
        self._emit_inline()
        for _ in range(5):
            process_inline_deliveries(max_attempts=5)
            d = OutboxDelivery.objects.get()
            if d.status == OutboxDelivery.Status.DEAD:
                break
        d = OutboxDelivery.objects.get()
        self.assertEqual(d.status, OutboxDelivery.Status.DEAD)
        self.assertEqual(d.attempts, 5)
        self.assertIn("consumer boom", d.last_error)

    def test_notification_lane_untouched_when_no_inline_consumer(self):
        # With no inline consumer for this type, a plain notification emit creates
        # zero delivery rows — the enqueue lane is the only lane exercised.
        emit("test_event", user_id=1, title="T", message="M")
        self.assertEqual(OutboxDelivery.objects.count(), 0)
        self.assertEqual(OutboxEvent.objects.filter(event_type="test_event").count(), 1)
