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

from django.db import transaction
from django.dispatch import Signal

# A single typed signal for all domain events. The outbox relay
# (apps/core/tasks.process_outbox) re-fires this signal for each durably-stored
# event; receivers register in their app's AppConfig.ready() and stay
# forward-compatible by accepting **kwargs.
domain_event = Signal()


def emit(event_type: str, *, user_id: int, title: str, message: str,
         community_id: int | None = None,
         conversation_id: int | None = None,
         contribution_id: int | None = None,
         join_request_id: int | None = None) -> None:
    """
    Emit a domain event durably (ADR-0006).

    Writes an OutboxEvent row in the CURRENT transaction — atomic with the state
    change when called inside an ``atomic`` block, so a rolled-back transaction
    discards the event (no phantoms) and a process/broker crash never loses it.
    The ``process_outbox`` relay delivers it at-least-once to consumers.

    Signature is unchanged from the previous on_commit/signal implementation, so
    all ~30 call sites are untouched. Payload values must be JSON-serialisable
    primitives (IDs, strings, numbers) — never ORM objects.

    Args:
        event_type: Identifies the event (maps to Notification.notification_type).
        user_id: Primary recipient of the resulting notification.
        title / message: Notification text.
        *_id: Optional FK hints for deep-linking.
    """
    from .models import OutboxEvent

    OutboxEvent.objects.create(
        event_type=event_type,
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
