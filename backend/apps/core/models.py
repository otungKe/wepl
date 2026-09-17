"""
Transactional outbox (Phase 2, ADR-0006).

`emit()` (apps/core/events.py) writes an OutboxEvent row in the same DB
transaction as the state change. The `process_outbox` relay (apps/core/tasks.py)
delivers events at-least-once to consumers, so an event is never lost in the gap
between COMMIT and dispatch.
"""
from django.db import models
from django.utils import timezone


class OutboxEvent(models.Model):
    class Status(models.TextChoices):
        PENDING   = 'PENDING',   'Pending'
        PROCESSED = 'PROCESSED', 'Processed'
        DEAD      = 'DEAD',      'Dead-lettered'

    event_type   = models.CharField(max_length=64, db_index=True)
    # The typed body of the event (event-type-specific JSON primitives). For
    # notification-shaped events this holds the notification fields; other event
    # types carry their own shape. Wrapped by the envelope below (ADR-0029).
    payload      = models.JSONField(default=dict)

    # ── Envelope (ADR-0029) ────────────────────────────────────────────────
    # Routing/identity metadata common to every event, independent of the body.
    # aggregate_key orders/locks events per subject; dedup_key is the business
    # dedup handle (money consumers dedupe on it — Stage 2). Both blank for
    # notification events, whose dedup stays on the outbox row id for now.
    aggregate_key  = models.CharField(max_length=128, blank=True, default='', db_index=True)
    dedup_key      = models.CharField(max_length=128, blank=True, default='', db_index=True)
    occurred_at    = models.DateTimeField(default=timezone.now)
    schema_version = models.PositiveSmallIntegerField(default=1)

    status       = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING,
    )
    attempts     = models.PositiveIntegerField(default=0)
    last_error   = models.TextField(blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            # The relay claim: oldest PENDING first.
            models.Index(fields=['status', 'created_at'], name='outbox_status_created_idx'),
        ]

    def __str__(self):
        return f"Outbox-{self.id} [{self.event_type}] {self.status}"


class WorkerHeartbeat(models.Model):
    """Liveness stamp for a scheduled (beat) task — OP-2 System Health.

    Each watched task upserts ``last_seen`` on completion (via a Celery
    ``task_postrun`` signal, see ``apps/core/health.py``). The health workspace
    flags a task whose stamp has gone stale — the signal that a worker/beat has
    silently died. DB-backed rather than cache-backed because web and worker are
    separate processes and no shared Django cache is configured.
    """
    task_name = models.CharField(max_length=128, primary_key=True)
    last_seen = models.DateTimeField()

    def __str__(self):
        return f"Heartbeat[{self.task_name}] @ {self.last_seen:%Y-%m-%d %H:%M:%S}"
