"""
Reminders — user-controlled scheduled alerts.

Each reminder fires a Notification at scheduled_for, then (if recurring)
advances next_fire_at by the recurrence interval.

The Celery beat task 'fire-due-reminders' runs every 30 minutes and
processes all reminders where next_fire_at <= now and is_active=True.
"""
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import F
from django.utils import timezone

_RECURRENCE_STEP = {
    'daily':   timedelta(days=1),
    'weekly':  timedelta(weeks=1),
    'monthly': timedelta(days=30),
}


class Reminder(models.Model):

    TYPE_CHOICES = [
        ('contribution_due',   'Contribution Due'),
        ('welfare_contrib',    'Welfare Contribution'),
        ('advance_repayment',  'Advance Repayment'),
        ('standing_order',     'Standing Order'),
        ('custom',             'Custom'),
    ]

    RECURRENCE_CHOICES = [
        ('none',    'One-time'),
        ('daily',   'Daily'),
        ('weekly',  'Weekly'),
        ('monthly', 'Monthly'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reminders',
    )

    reminder_type = models.CharField(max_length=25, choices=TYPE_CHOICES, default='custom')
    title         = models.CharField(max_length=150)
    note          = models.TextField(blank=True, default='')

    # Optional link to a specific contribution or community
    contribution_id = models.PositiveIntegerField(null=True, blank=True)
    community_id    = models.PositiveIntegerField(null=True, blank=True)

    # Scheduling
    scheduled_for = models.DateTimeField(help_text='When to fire this reminder (or first fire if recurring)')
    recurrence    = models.CharField(max_length=10, choices=RECURRENCE_CHOICES, default='none')
    next_fire_at  = models.DateTimeField(db_index=True)  # maintained by the task

    # State
    is_active   = models.BooleanField(default=True, db_index=True)
    last_sent_at = models.DateTimeField(null=True, blank=True)
    send_count  = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['next_fire_at']
        indexes = [
            models.Index(fields=['user', 'is_active', 'next_fire_at'], name='reminder_user_active_fire_idx'),
        ]

    def save(self, *args, **kwargs):
        # On first save, seed next_fire_at from scheduled_for
        if not self.pk and not self.next_fire_at:
            self.next_fire_at = self.scheduled_for
        super().save(*args, **kwargs)

    def _next_future_fire(self, now) -> 'timezone.datetime':
        """Next fire strictly after *now*, skipping occurrences missed during
        downtime — so a long-overdue recurring reminder fires once and reschedules
        ahead, rather than back-firing a burst of stale alerts (catch-up policy)."""
        step = _RECURRENCE_STEP[self.recurrence]
        nxt = self.next_fire_at + step
        while nxt <= now:
            nxt += step
        return nxt

    def claim(self) -> bool:
        """Atomically reserve this occurrence and return whether *this* caller won.

        The reservation is a single conditional UPDATE guarded by the value we
        read (``is_active=True`` and the same ``next_fire_at``). Under concurrent
        beats/workers exactly one caller's UPDATE matches; the rest get 0 rows and
        return False — so a reminder is dispatched at most once per occurrence
        (no double-fire). Claim happens *before* sending, so a crash mid-dispatch
        drops that occurrence rather than risking a duplicate.
        """
        now = timezone.now()
        seen_fire = self.next_fire_at
        updates = {'last_sent_at': now, 'send_count': F('send_count') + 1}
        if self.recurrence == 'none':
            updates['is_active'] = False
        else:
            updates['next_fire_at'] = self._next_future_fire(now)

        claimed = (
            Reminder.objects
            .filter(pk=self.pk, is_active=True, next_fire_at=seen_fire)
            .update(**updates)
        )
        return claimed == 1

    def __str__(self):
        return f"[{self.reminder_type}] {self.title} — {self.user.phone_number}"
