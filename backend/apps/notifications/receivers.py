"""
Notification receivers — domain event → Celery notification task.

This module is the ONLY place where apps.notifications knows about
the domain event bus. Services know nothing about this file.

To add a new consumer (e.g. push notifications, SMS):
    1. Create apps/push/receivers.py
    2. Connect it in apps/push/apps.py:ready()
    3. No service code changes required.
"""

from django.dispatch import receiver

from apps.core.events import domain_event


@receiver(domain_event)
def dispatch_notification(
    sender,
    event_type,
    user_id,
    title,
    message,
    outbox_event_id=None,  # P2-03: UUID for idempotent dedupe across relay retries
    community_id=None,
    conversation_id=None,
    contribution_id=None,
    join_request_id=None,
    **kwargs,   # forward-compatible: ignore unknown future fields
):
    """
    Convert every domain event into an async Celery notification task.

    outbox_event_id is forwarded to the task so it can deduplicate on it,
    preventing duplicate notifications when the relay re-delivers an event.
    """
    from .tasks import send_notification

    send_notification.delay(
        user_id=user_id,
        notification_type=event_type,
        title=title,
        message=message,
        community_id=community_id,
        conversation_id=conversation_id,
        contribution_id=contribution_id,
        join_request_id=join_request_id,
        outbox_event_id=outbox_event_id,
    )
