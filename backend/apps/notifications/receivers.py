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
    user_id=None,
    title=None,
    message=None,
    community_id=None,
    conversation_id=None,
    contribution_id=None,
    join_request_id=None,
    outbox_event_id=None,
    **kwargs,   # forward-compatible: ignore unknown future fields
):
    """
    Convert a *notification-shaped* domain event into an async Celery notification
    task.

    The relay re-fires domain_event for EVERY outbox event, including general
    (non-notification) facts emitted via emit_event() — e.g. money events like
    payment.settled (ADR-0029). Those carry no user_id, so this receiver skips
    them: they are the inline lane's business, not a notification. Notification
    events always carry a user_id, so this guard is a no-op for them.

    The import of send_notification is deferred to the function body so this
    module can be imported at AppConfig.ready() time without triggering circular
    imports (apps may not be fully loaded at module-import time).
    """
    if user_id is None:
        return

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
        event_id=outbox_event_id,
    )
