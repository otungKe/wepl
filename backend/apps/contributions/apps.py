from django.apps import AppConfig


class ContributionsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.contributions'

    def ready(self):
        # Register the contribution authorization policy (ADR-0009).
        from . import policies  # noqa: F401
        # Register the inline settlement consumer (ADR-0028/0029 Stage 2).
        from . import settlement_consumer
        settlement_consumer.register()
