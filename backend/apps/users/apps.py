from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.users'

    def ready(self):
        # Register the KYC exception renderer with Core's registry (ADR-0031).
        from . import exceptions  # noqa: F401
