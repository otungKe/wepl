from celery import shared_task
from .services import NotificationService


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    queue='notifications',
)
def send_notification(
    self,
    user_id,
    notification_type,
    title,
    message,
    community_id=None,
    conversation_id=None,
    contribution_id=None,
    join_request_id=None,
):
    """
    Create a Notification record asynchronously.
    Called via .delay() or .apply_async() from service layer.
    Retries up to 3 times on failure with 30-second backoff.
    """
    try:
        NotificationService.create(
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            message=message,
            community_id=community_id,
            conversation_id=conversation_id,
            contribution_id=contribution_id,
            join_request_id=join_request_id,
        )
    except Exception as exc:
        raise self.retry(exc=exc)
