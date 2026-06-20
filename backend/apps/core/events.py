"""
Domain event bus — transactional outbox edition (Phase 2).

Services call emit() to announce that something happened.
They do NOT know which apps are listening or what those apps do with the event.

The event is persisted to the OutboxEvent table inside the same DB transaction
as the state change, so no event can be lost even if the process dies between
commit and in-process dispatch.  A fast-path Celery task fires on_commit for
low-latency delivery; the relay worker (apps.core.tasks.relay_outbox_events)
recovers any events missed due to a crash.

Receiver registration is still done in each consumer app's AppConfig.ready()
(e.g. apps/notifications/apps.py).  Consumers must be idempotent — they receive
the outbox event UUID and may deduplicate on it.

Usage (unchanged from Phase 0):
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

from django.db import transaction
from django.dispatch import Signal

logger = logging.getLogger(__name__)

# In-process delivery signal — consumers connect to this in AppConfig.ready().
# Senders always pass event_type=str plus event-specific kwargs.
# Receivers should use **kwargs to stay forward-compatible as new fields are added.
domain_event = Signal()


def emit(
    event_type: str,
    *,
    user_id: int,
    title: str,
    message: str,
    community_id: int | None = None,
    conversation_id: int | None = None,
    contribution_id: int | None = None,
    join_request_id: int | None = None,
) -> None:
    """
    Emit a domain event durably.

    Writes an OutboxEvent row inside the current transaction (or its own
    transaction if called outside one).  After commit, schedules
    deliver_outbox_event for low-latency delivery via the in-process Signal.
    The relay worker is the safety net for events lost to process crashes.

    All payload values must be JSON-serializable primitives — never pass ORM
    objects, which may be garbage-collected before delivery.
    """
    from .models import OutboxEvent

    payload = {
        'user_id':         user_id,
        'title':           title,
        'message':         message,
        'community_id':    community_id,
        'conversation_id': conversation_id,
        'contribution_id': contribution_id,
        'join_request_id': join_request_id,
    }

    event = OutboxEvent.objects.create(event_type=event_type, payload=payload)
    event_id = str(event.id)

    def _schedule_delivery():
        from apps.core.tasks import deliver_outbox_event
        deliver_outbox_event.delay(event_id)

    transaction.on_commit(_schedule_delivery)
