"""
Celery task: fire due reminders.

Runs every 30 minutes via django-celery-beat.
For each active reminder whose next_fire_at has elapsed:
  1. Creates a Notification for the user
  2. Calls reminder.advance() to update next_fire_at (or deactivate one-time)
"""
import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name='apps.reminders.tasks.fire_due_reminders', bind=True, max_retries=3)
def fire_due_reminders(self):
    from .models import Reminder
    from apps.notifications.services import NotificationService

    now = timezone.now()

    due = Reminder.objects.filter(
        is_active=True,
        next_fire_at__lte=now,
    ).select_related('user')

    fired = 0
    for reminder in due:
        try:
            NotificationService.create(
                user=reminder.user,
                notification_type='reminder',
                title=reminder.title,
                message=reminder.note or reminder.title,
                contribution_id=reminder.contribution_id,
                community_id=reminder.community_id,
            )
            reminder.advance()
            fired += 1
        except Exception:
            logger.exception("Failed to fire reminder id=%s user=%s", reminder.id, reminder.user_id)

    logger.info("fire_due_reminders: fired %d reminders at %s", fired, now)
    return fired
