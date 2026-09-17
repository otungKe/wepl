from django.apps import AppConfig


class ControlsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.controls'

    def ready(self):
        # Register the control exception renderers with Core's registry (ADR-0031).
        from . import exceptions  # noqa: F401
