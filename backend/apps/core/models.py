import uuid

from django.db import models


class OutboxEvent(models.Model):
    """
    Transactional outbox — persisted inside the same DB transaction as the
    state change that emitted the event.  A relay worker delivers events
    at-least-once to idempotent consumers.
    """

    class Status(models.TextChoices):
        PENDING     = 'pending',     'Pending'
        PROCESSING  = 'processing',  'Processing'
        DELIVERED   = 'delivered',   'Delivered'
        DEAD_LETTER = 'dead_letter', 'Dead Letter'

    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_type   = models.CharField(max_length=100, db_index=True)
    payload      = models.JSONField()
    status       = models.CharField(
        max_length=15, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    attempts     = models.PositiveSmallIntegerField(default=0)
    error        = models.TextField(blank=True)
    created_at   = models.DateTimeField(auto_now_add=True, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at']
        indexes  = [models.Index(fields=['status', 'created_at'], name='outbox_status_created_idx')]
        verbose_name        = 'Outbox Event'
        verbose_name_plural = 'Outbox Events'

    def __str__(self):
        return f'{self.event_type} [{self.status}] {self.id}'
