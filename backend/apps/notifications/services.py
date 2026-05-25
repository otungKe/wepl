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
    ):
        """
        Accepts either a User instance (``user=``) or a plain integer
        (``user_id=``) so it can be called safely from ``transaction.on_commit``
        callbacks where the ORM object may no longer be in scope.
        """
        if user_id is None and user is not None:
            user_id = user.id if hasattr(user, 'id') else user

        return Notification.objects.create(
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            message=message,
            community_id=community_id,
            conversation_id=conversation_id,
            contribution_id=contribution_id,
            join_request_id=join_request_id,
        )

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
