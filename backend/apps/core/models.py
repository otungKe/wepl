"""
Transactional outbox (Phase 2, ADR-0006).

`emit()` (apps/core/events.py) writes an OutboxEvent row in the same DB
transaction as the state change. The `process_outbox` relay (apps/core/tasks.py)
delivers events at-least-once to consumers, so an event is never lost in the gap
between COMMIT and dispatch.
"""
from django.db import models


class OutboxEvent(models.Model):
    class Status(models.TextChoices):
        PENDING   = 'PENDING',   'Pending'
        PROCESSED = 'PROCESSED', 'Processed'
        DEAD      = 'DEAD',      'Dead-lettered'

    event_type   = models.CharField(max_length=64, db_index=True)
    payload      = models.JSONField(default=dict)
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
