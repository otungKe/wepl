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
from django.utils import timezone


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

    def advance(self) -> None:
        """
        Mark as fired and compute the next fire time (if recurring).
        Deactivates one-time reminders after firing.
        """
        now = timezone.now()
        self.last_sent_at = now
        self.send_count  += 1

        if self.recurrence == 'none':
            self.is_active = False
        elif self.recurrence == 'daily':
            self.next_fire_at = self.next_fire_at + timedelta(days=1)
        elif self.recurrence == 'weekly':
            self.next_fire_at = self.next_fire_at + timedelta(weeks=1)
        elif self.recurrence == 'monthly':
            self.next_fire_at = self.next_fire_at + timedelta(days=30)

        self.save(update_fields=['last_sent_at', 'send_count', 'is_active', 'next_fire_at'])

    def __str__(self):
        return f"[{self.reminder_type}] {self.title} — {self.user.phone_number}"
