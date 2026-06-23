from django.apps import AppConfig


class ContributionsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.contributions'

    def ready(self):
        # Register the contribution authorization policy (ADR-0009).
        from . import policies  # noqa: F401
