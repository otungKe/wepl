from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.notifications'

    def ready(self):
        # Connect the domain-event receiver so every emit() call
        # results in a send_notification Celery task being queued.
        import apps.notifications.receivers  # noqa: F401
