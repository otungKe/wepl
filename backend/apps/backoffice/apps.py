from django.apps import AppConfig


class BackofficeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.backoffice"
    verbose_name = "Back Office (Operations Console)"

    def ready(self):
        from .flagged_actions import register_all
        register_all()
