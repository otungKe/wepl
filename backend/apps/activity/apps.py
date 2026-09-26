from django.apps import AppConfig


class ActivityConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.activity'

    def ready(self):
        # The feed is written from domain facts, not by the apps that cause them.
        from .consumers import register
        register()
