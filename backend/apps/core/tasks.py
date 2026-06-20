"""
Outbox relay tasks (P2-02).

Two entry points:
  deliver_outbox_event(event_id)  — fast-path, scheduled on_commit by emit()
  relay_outbox_events()           — beat-driven safety net for missed events
"""

import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)

MAX_ATTEMPTS   = 5
RELAY_LAG_SECS = 30   # relay picks up events older than this (missed fast-path)


@shared_task(
    bind=True,
    max_retries=MAX_ATTEMPTS - 1,
    default_retry_delay=15,
    queue='default',
    name='apps.core.tasks.deliver_outbox_event',
)
def deliver_outbox_event(self, event_id: str) -> None:
    """
    Deliver a single OutboxEvent via the in-process Signal.

    Idempotent: marks PROCESSING before dispatch, DELIVERED on success.
    Retries up to MAX_ATTEMPTS times with exponential backoff; moves to
    DEAD_LETTER when retries are exhausted.
    """
    from .models import OutboxEvent
    from .events import domain_event

    try:
        event = OutboxEvent.objects.get(pk=event_id)
    except OutboxEvent.DoesNotExist:
        logger.warning("deliver_outbox_event: event %s not found", event_id)
        return

    if event.status == OutboxEvent.Status.DELIVERED:
        return  # already delivered (relay ran first or duplicate task)

    updated = OutboxEvent.objects.filter(
        pk=event_id, status__in=[OutboxEvent.Status.PENDING, OutboxEvent.Status.PROCESSING]
    ).update(status=OutboxEvent.Status.PROCESSING, attempts=event.attempts + 1)

    if not updated:
        return  # concurrent worker already claimed it

    try:
        domain_event.send(
            sender=event.event_type,
            event_type=event.event_type,
            outbox_event_id=event_id,
            **event.payload,
        )
        OutboxEvent.objects.filter(pk=event_id).update(
            status=OutboxEvent.Status.DELIVERED,
            processed_at=timezone.now(),
            error='',
        )
    except Exception as exc:
        attempts = event.attempts + 1
        if attempts >= MAX_ATTEMPTS:
            OutboxEvent.objects.filter(pk=event_id).update(
                status=OutboxEvent.Status.DEAD_LETTER,
                error=str(exc),
            )
            logger.error(
                "OutboxEvent %s moved to dead-letter after %d attempts: %s",
                event_id, attempts, exc,
            )
        else:
            OutboxEvent.objects.filter(pk=event_id).update(
                status=OutboxEvent.Status.PENDING,
                error=str(exc),
            )
            raise self.retry(exc=exc, countdown=15 * (2 ** (attempts - 1)))


@shared_task(
    queue='default',
    name='apps.core.tasks.relay_outbox_events',
)
def relay_outbox_events() -> None:
    """
    Beat-driven safety net: re-queue any PENDING events old enough to have
    been missed by the fast-path on_commit task.
    """
    from .models import OutboxEvent

    cutoff = timezone.now() - timezone.timedelta(seconds=RELAY_LAG_SECS)
    stale = OutboxEvent.objects.filter(
        status=OutboxEvent.Status.PENDING,
        created_at__lte=cutoff,
    ).values_list('id', flat=True)[:200]

    for event_id in stale:
        deliver_outbox_event.delay(str(event_id))
        logger.info("relay_outbox_events: re-queued %s", event_id)

    dead_count = OutboxEvent.objects.filter(status=OutboxEvent.Status.DEAD_LETTER).count()
    if dead_count:
        logger.warning(
            "relay_outbox_events: %d event(s) in dead-letter — review in admin",
            dead_count,
        )
