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

# A single typed signal for all domain events.
# Senders always pass event_type=str; additional kwargs are event-specific.
# Receivers should use **kwargs to stay forward-compatible as new fields are added.
domain_event = Signal()


def emit(event_type: str, *, user_id: int, title: str, message: str,
         community_id: int | None = None,
         conversation_id: int | None = None,
         contribution_id: int | None = None,
         join_request_id: int | None = None) -> None:
    """
    Emit a domain event AFTER the current transaction commits.

    Safe to call inside or outside atomic blocks — the signal fires only
    after the DB transaction commits, so receivers always see consistent state.

    All payload values must be JSON-serializable primitives (IDs, strings,
    numbers) — never pass ORM objects, which may be garbage-collected by the
    time on_commit fires.

    Args:
        event_type: Identifies the event (maps to Notification.notification_type).
        user_id: Primary recipient of the resulting notification.
        title: Short notification title.
        message: Full notification body.
        community_id: Optional FK hint for deep-linking.
        conversation_id: Optional FK hint for deep-linking.
        contribution_id: Optional FK hint for deep-linking.
        join_request_id: Optional FK hint for deep-linking.
    """
    payload = {
        'user_id':         user_id,
        'title':           title,
        'message':         message,
        'community_id':    community_id,
        'conversation_id': conversation_id,
        'contribution_id': contribution_id,
        'join_request_id': join_request_id,
    }

    def _send():
        domain_event.send(sender=event_type, event_type=event_type, **payload)

    transaction.on_commit(_send)
