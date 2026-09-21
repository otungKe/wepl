"""
Outbox relay (Phase 2, ADR-0006).

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
                # Dispatch inside a SAVEPOINT. A receiver that raises a *database*
                # error would otherwise leave the whole transaction aborted, and
                # the bookkeeping write in the except branch below would raise
                # too ("current transaction is aborted") — so the event would
                # never count an attempt and never dead-letter; the task would
                # just die. Rolling back to the savepoint discards the receiver's
                # partial writes and leaves this transaction usable.
                with transaction.atomic():
                    # Re-fire the domain event to all registered receivers. The
                    # outbox event id rides along so consumers can dedupe
                    # (at-least-once).
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


@shared_task(queue='financial')
def process_inline_deliveries(max_deliveries: int = 500, max_attempts: int = 5) -> dict:
    """Deliver OutboxDelivery rows to inline (financial-grade) consumers
    (ADR-0029 Stage 2, the ``inline_atomic`` lane).

    Each delivery is claimed with ``select_for_update(skip_locked=True)`` and its
    consumer's handler is run *synchronously inside the same transaction that acks
    the row* — so the handler's effect (e.g. a journal posting) and the delivery
    ack commit together. Handlers must be idempotent (money dedupes via
    ``post_journal``'s idempotency key), because a crash between the handler and
    the ack re-delivers the row. Independent per-delivery attempts/dead-letter:
    one consumer's failure never touches another's rows or the notification lane.
    """
    from .events import _INLINE_CONSUMERS
    from .models import OutboxDelivery

    processed = 0
    dead = 0

    for _ in range(max_deliveries):
        with transaction.atomic():
            delivery = (
                OutboxDelivery.objects
                .select_for_update(skip_locked=True)
                .filter(status=OutboxDelivery.Status.PENDING)
                .select_related('outbox_event')
                .order_by('id')
                .first()
            )
            if delivery is None:
                break

            try:
                consumer = _INLINE_CONSUMERS.get(delivery.consumer_name)
                if consumer is None:
                    # A delivery row for a consumer this worker doesn't have
                    # registered (mid-deploy skew, or a removed consumer). Fail it
                    # so it retries — a rolling deploy resolves it, and it never
                    # silently vanishes.
                    raise RuntimeError(
                        f"No inline consumer registered for '{delivery.consumer_name}'")
                # Run the handler inside a SAVEPOINT. The handler's effect still
                # commits with the ack (the savepoint is released into this
                # transaction on success), so the exactly-once guarantee is
                # unchanged. But a handler that raises a *database* error — a
                # constraint violation, a bad query — would otherwise abort the
                # whole transaction, and the bookkeeping write in the except
                # branch below would raise too ("current transaction is
                # aborted"): the delivery would never count an attempt and never
                # dead-letter, and the task would die instead. Rolling back to
                # the savepoint discards the handler's partial writes and leaves
                # this transaction usable to record the failure.
                with transaction.atomic():
                    consumer.handler(delivery.outbox_event)
                delivery.status = OutboxDelivery.Status.PROCESSED
                delivery.processed_at = timezone.now()
                delivery.save(update_fields=['status', 'processed_at'])
                processed += 1
            except Exception as exc:
                delivery.attempts += 1
                delivery.last_error = str(exc)[:1000]
                if delivery.attempts >= max_attempts:
                    delivery.status = OutboxDelivery.Status.DEAD
                    dead += 1
                    logger.error(
                        "process_inline_deliveries: delivery %s (%s) dead-lettered "
                        "after %d attempts: %s",
                        delivery.id, delivery.consumer_name, delivery.attempts, exc,
                    )
                else:
                    logger.warning(
                        "process_inline_deliveries: delivery %s (%s) failed "
                        "(attempt %d): %s",
                        delivery.id, delivery.consumer_name, delivery.attempts, exc,
                    )
                delivery.save(update_fields=['attempts', 'last_error', 'status'])

    if dead:
        _alert(f"Inline delivery dead-lettered {dead} row(s)", {'dead': dead})

    if processed or dead:
        logger.info("process_inline_deliveries: processed=%d dead=%d", processed, dead)
    return {'processed': processed, 'dead': dead}
