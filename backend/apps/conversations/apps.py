from django.apps import AppConfig


class ConversationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.conversations'

    def ready(self):
        # Register the conversation/message authorization policy (ADR-0009).
        from . import policies  # noqa: F401
