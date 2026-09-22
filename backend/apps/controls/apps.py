from django.apps import AppConfig


class ControlsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.controls'

    def ready(self):
        # Register the control exception renderers with Core's registry (ADR-0031).
        from . import exceptions  # noqa: F401
        # Install the limits/risk gate into the ledger's posting chokepoint
        # (ADR-0007). The ledger owns the hook; controls owns the policy.
        from apps.ledger.chokepoint import register_pre_posting_check
        from .engine import enforce_controls
        register_pre_posting_check(enforce_controls)
        # React to a decided EDD case by releasing the movement it was opened
        # over, so the case ledger does not write controls' rows (ADR-0033).
        from . import cases
        cases.register()
