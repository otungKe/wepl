"""
Domain event bus.

Services call emit() to announce that something happened.
They do NOT know which apps are listening or what those apps do with the event.

Receiver registration happens in each consumer app's AppConfig.ready()
(e.g. apps/notifications/apps.py).

Adding a new consumer (push notifications, SMS, analytics) means adding a
new receiver — no service code needs to change.

Usage in a service:
    from apps.core.events import emit

    emit(
        'advance_approved',
        user_id=advance.borrower.id,
        title="Emergency advance approved!",
        message="Your KES 5,000 advance is being sent to your M-Pesa.",
        contribution_id=contribution.id,
    )
"""

import logging
from dataclasses import dataclass
from typing import Callable

from django.db import transaction
from django.dispatch import Signal

logger = logging.getLogger(__name__)

# A single typed signal for all domain events. The outbox relay
# (apps/core/tasks.process_outbox) re-fires this signal for each durably-stored
# event; receivers register in their app's AppConfig.ready() and stay
# forward-compatible by accepting **kwargs. This is the *enqueue lane* — fan-out
# to every receiver, best-effort (notifications).
domain_event = Signal()


# ── Inline consumer registry (ADR-0029 Stage 2, the inline_atomic lane) ───────
# Unlike the domain_event signal (fan-out-to-all, enqueue lane), an inline
# consumer names the exact event types it handles and runs synchronously in the
# delivery relay, acking its own OutboxDelivery row atomically with its effect.
# Consumers register from their app's AppConfig.ready() — Core knows only the
# opaque name, event types, and an idempotent handler (the policy.py discipline).
@dataclass(frozen=True)
class InlineConsumer:
    name: str
    event_types: frozenset
    handler: Callable  # handler(event: OutboxEvent) -> None ; MUST be idempotent


_INLINE_CONSUMERS: dict[str, InlineConsumer] = {}


def register_inline_consumer(name: str, event_types, handler: Callable) -> None:
    """Register an inline (financial-grade) consumer. Idempotent handler required:
    at-least-once delivery means the handler may run more than once for one fact —
    money consumers dedupe via ``post_journal``'s idempotency key (ADR-0004)."""
    if name in _INLINE_CONSUMERS:
        logger.warning("Inline consumer '%s' is being overwritten.", name)
    _INLINE_CONSUMERS[name] = InlineConsumer(name, frozenset(event_types), handler)


def inline_consumers_for(event_type: str) -> list[InlineConsumer]:
    return [c for c in _INLINE_CONSUMERS.values() if event_type in c.event_types]


def emit(event_type: str, *, user_id: int, title: str, message: str,
         community_id: int | None = None,
         conversation_id: int | None = None,
         contribution_id: int | None = None,
         join_request_id: int | None = None,
         aggregate_key: str = '',
         dedup_key: str = '',
         schema_version: int = 1) -> None:
    """
    Emit a domain event durably (transactional outbox, ADR-0006/ADR-0029).

    Writes an OutboxEvent row in the CURRENT transaction — atomic with the state
    change when called inside an ``atomic`` block, so a rolled-back transaction
    discards the event (no phantoms) and a process/broker crash never loses it.
    The ``process_outbox`` relay delivers it at-least-once to consumers.

    The row carries an **envelope** (aggregate_key, dedup_key, occurred_at,
    schema_version — ADR-0029) around the **body** in ``payload``. The
    notification fields are the body of notification-shaped events; the envelope
    kwargs are optional and default to blank, so all existing (~30) call sites are
    untouched (Stage 1 is additive, zero behaviour change). Payload values must be
    JSON-serialisable primitives (IDs, strings, numbers) — never ORM objects.

    Args:
        event_type: Identifies the event (maps to Notification.notification_type).
        user_id: Primary recipient of the resulting notification.
        title / message: Notification text.
        *_id: Optional FK hints for deep-linking.
        aggregate_key: Envelope — orders/locks events per subject (e.g.
            ``"payment:123"``). Blank for notification events.
        dedup_key: Envelope — business dedup handle; money consumers dedupe on it
            (Stage 2). Blank for notification events.
        schema_version: Envelope — body schema version for this event_type.
    """
    from .models import OutboxDelivery, OutboxEvent

    event = OutboxEvent.objects.create(
        event_type=event_type,
        aggregate_key=aggregate_key,
        dedup_key=dedup_key,
        schema_version=schema_version,
        payload={
            'user_id':         user_id,
            'title':           title,
            'message':         message,
            'community_id':    community_id,
            'conversation_id': conversation_id,
            'contribution_id': contribution_id,
            'join_request_id': join_request_id,
        },
    )

    # Fan out one delivery row per subscribed inline consumer, in the SAME
    # transaction as the event (ADR-0029 Stage 2) — so the delivery obligation is
    # as durable as the fact itself, with no unbounded relay scan. The enqueue
    # lane (notifications) is unaffected; it is still delivered by process_outbox
    # via the domain_event signal. With no inline consumers registered this is a
    # no-op — zero behaviour change.
    consumers = inline_consumers_for(event_type)
    if consumers:
        OutboxDelivery.objects.bulk_create(
            [OutboxDelivery(outbox_event=event, consumer_name=c.name)
             for c in consumers]
        )


def requeue_outbox_event(event_id: int):
    """Return a dead-lettered event to the delivery queue — the one sanctioned
    way to retry a DEAD outbox event (OP-2 health workspace). Resets attempts and
    clears the last error so the relay picks it up fresh. Raises if the event is
    not dead-lettered (PENDING/PROCESSED must not be disturbed)."""
    from django.core.exceptions import ValidationError

    from .models import OutboxEvent

    with transaction.atomic():
        event = OutboxEvent.objects.select_for_update().get(pk=event_id)
        if event.status != OutboxEvent.Status.DEAD:
            raise ValidationError("Only dead-lettered events can be requeued.")
        event.status = OutboxEvent.Status.PENDING
        event.attempts = 0
        event.last_error = ""
        event.processed_at = None
        event.save(update_fields=["status", "attempts", "last_error", "processed_at"])
    return event
