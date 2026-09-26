from django.apps import AppConfig


class VerificationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.verification'
    verbose_name = 'Identity Verification (case ledger)'

    def ready(self):
        # Answer for identity data when an account closes or is exported (step 8).
        from . import lifecycle
        lifecycle.register()
