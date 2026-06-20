from django.contrib.auth import get_user_model

from .models import Notification

User = get_user_model()


class NotificationService:

    @staticmethod
    def create(
        notification_type,
        title,
        message,
        user=None,
        user_id=None,
        community_id=None,
        conversation_id=None,
        contribution_id=None,
        join_request_id=None,
        event_id=None,
    ):
        """
        Create a Notification record and enqueue an FCM push to the user's
        registered devices (Issue 19).

        Accepts either a User instance (``user=``) or a plain integer (``user_id=``).

        ``event_id`` (the outbox OutboxEvent id) makes creation idempotent: the
        relay is at-least-once, so a redelivered event must not duplicate the row.
        """
        if user_id is None and user is not None:
            user_id = user.id if hasattr(user, 'id') else user

        fields = dict(
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            message=message,
            community_id=community_id,
            conversation_id=conversation_id,
            contribution_id=contribution_id,
            join_request_id=join_request_id,
        )
        if event_id is not None:
            notification, _ = Notification.objects.get_or_create(
                event_id=event_id, defaults=fields,
            )
        else:
            notification = Notification.objects.create(**fields)
        # FCM dispatch is handled by the send_notification Celery task that
        # calls this method — do NOT dispatch here to avoid double-firing.
        return notification

    @staticmethod
    def get_for_user(user):
        return Notification.objects.filter(user=user)

    @staticmethod
    def unread_count(user):
        return Notification.objects.filter(user=user, is_read=False).count()

    @staticmethod
    def mark_read(notification_id, user):
        Notification.objects.filter(id=notification_id, user=user).update(is_read=True)

    @staticmethod
    def mark_all_read(user):
        Notification.objects.filter(user=user, is_read=False).update(is_read=True)

    @staticmethod
    def delete_one(notification_id, user):
        Notification.objects.filter(id=notification_id, user=user).delete()

    @staticmethod
    def delete_all(user):
        Notification.objects.filter(user=user).delete()

    # ── Device registration ──────────────────────────────────────────────────

    @staticmethod
    def register_device(user, fcm_token, platform='android'):
        """
        Upsert a device token for a user.

        Called on every app launch so the token stays fresh — FCM tokens rotate
        periodically and the old token becomes invalid (Issue 19).
        """
        from .models import UserDevice
        device, _ = UserDevice.objects.update_or_create(
            fcm_token=fcm_token,
            defaults={'user': user, 'platform': platform},
        )
        return device

    @staticmethod
    def unregister_device(user, fcm_token):
        """Remove a token on logout so stale tokens don't accumulate."""
        from .models import UserDevice
        UserDevice.objects.filter(user=user, fcm_token=fcm_token).delete()
