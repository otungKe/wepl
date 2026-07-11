"""
Outbox relay (ADR-0006).

`process_outbox` delivers durably-stored OutboxEvents to consumers at-least-once.
Scheduled every few seconds (settings.CELERY_BEAT_SCHEDULE). Each event is claimed
with ``select_for_update(skip_locked=True)`` so multiple workers never double-send,
dispatched by re-firing the ``domain_event`` signal (preserving the pluggable
multi-consumer fan-out), then marked PROCESSED. Failures back off via ``attempts``
and dead-letter (status=DEAD) after ``max_attempts``.

Consumers must be idempotent (Notification dedupes on event_id) because a relay
crash between dispatch and the PROCESSED write can re-deliver an event.
"""
import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


def _alert(message: str, extra: dict) -> None:
    """Best-effort Sentry alert; always safe to call."""
    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            for k, v in extra.items():
                scope.set_extra(k, v)
            sentry_sdk.capture_message(message, level="error")
    except Exception:
        pass


@shared_task(queue='notifications')
def process_outbox(max_events: int = 500, max_attempts: int = 5) -> dict:
    from .events import domain_event
    from .models import OutboxEvent

    processed = 0
    dead = 0

    for _ in range(max_events):
        with transaction.atomic():
            event = (
                OutboxEvent.objects
                .select_for_update(skip_locked=True)
                .filter(status=OutboxEvent.Status.PENDING)
                .order_by('id')
                .first()
            )
            if event is None:
                break

            try:
                # Re-fire the domain event to all registered receivers. The outbox
                # event id rides along so consumers can dedupe (at-least-once).
                domain_event.send(
                    sender=event.event_type,
                    event_type=event.event_type,
                    outbox_event_id=event.id,
                    **event.payload,
                )
                event.status = OutboxEvent.Status.PROCESSED
                event.processed_at = timezone.now()
                event.save(update_fields=['status', 'processed_at'])
                processed += 1
            except Exception as exc:
                event.attempts += 1
                event.last_error = str(exc)[:1000]
                if event.attempts >= max_attempts:
                    event.status = OutboxEvent.Status.DEAD
                    dead += 1
                    logger.error(
                        "process_outbox: event %s dead-lettered after %d attempts: %s",
                        event.id, event.attempts, exc,
                    )
                else:
                    logger.warning(
                        "process_outbox: event %s failed (attempt %d): %s",
                        event.id, event.attempts, exc,
                    )
                event.save(update_fields=['attempts', 'last_error', 'status'])

    if dead:
        _alert(f"Outbox dead-lettered {dead} event(s)", {'dead': dead})

    if processed or dead:
        logger.info("process_outbox: processed=%d dead=%d", processed, dead)
    return {'processed': processed, 'dead': dead}
