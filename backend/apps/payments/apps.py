from django.apps import AppConfig


class PaymentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.payments'

    def ready(self):
        # Answer for saved payment methods when an account closes (step 8).
        from . import lifecycle
        lifecycle.register()
