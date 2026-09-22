from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.users'

    def ready(self):
        # Register the KYC exception renderer with Core's registry (ADR-0031).
        from . import exceptions  # noqa: F401

        # Tell a KYC applicant the outcome of their case. verification owns
        # the decision, users owns what the customer is told about it, so the
        # message is registered rather than imported (ADR-0033).
        from . import notifications
        notifications.register()
