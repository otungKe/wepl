"""
Celery task: fire due reminders (reminders hardening).

Runs every 30 minutes via django-celery-beat. Correctness under concurrency:

  * A cache-based distributed lock guards the whole tick, so a double-scheduled
    beat / a second worker doesn't run an overlapping pass. The lock auto-expires
    (< the beat interval) so a crash can't wedge it permanently.
  * Each reminder is *claimed* with an atomic conditional UPDATE before its
    notification is sent, so even if two passes overlap a reminder fires at most
    once per occurrence (no double-fire — the review's primary concern).
"""
import logging

from celery import shared_task
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

_LOCK_KEY = 'reminders:fire_due:lock'
_LOCK_TTL = 25 * 60  # seconds; < the 30-min beat interval so it self-heals


@shared_task(name='apps.reminders.tasks.fire_due_reminders', bind=True, max_retries=3)
def fire_due_reminders(self):
    from .models import Reminder
    from apps.notifications.services import NotificationService

    # Distributed lock — only one tick runs at a time (cache.add is atomic / NX).
    if not cache.add(_LOCK_KEY, '1', timeout=_LOCK_TTL):
        logger.info("fire_due_reminders: another tick holds the lock — skipping")
        return 0

    fired = 0
    try:
        now = timezone.now()
        # Suspended/archived communities fall silent (audit CR-2).
        # community_id is a loose integer link, so exclude via subquery.
        from apps.communities.models import Community
        inactive_ids = Community.objects.exclude(status='active').values('id')
        due = Reminder.objects.filter(
            is_active=True, next_fire_at__lte=now,
        ).exclude(community_id__in=inactive_ids).select_related('user')

        for reminder in due:
            # Reserve the occurrence first; skip if another pass already took it.
            if not reminder.claim():
                continue
            try:
                NotificationService.create(
                    user_id=reminder.user_id,
                    notification_type='reminder',
                    title=reminder.title,
                    message=reminder.note or reminder.title,
                    contribution_id=reminder.contribution_id,
                    community_id=reminder.community_id,
                )
                fired += 1
            except Exception:
                # Claimed but the send failed — log it; do not re-fire (at-most-once).
                logger.exception(
                    "Reminder %s claimed but notification send failed", reminder.id)
    finally:
        cache.delete(_LOCK_KEY)

    logger.info("fire_due_reminders: fired %d reminders", fired)
    return fired
