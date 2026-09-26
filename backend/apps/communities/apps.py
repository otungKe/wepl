from django.apps import AppConfig


class CommunitiesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.communities'

    def ready(self):
        # Register the community authorization policy (ADR-0009).
        from . import policies  # noqa: F401
        # Answer for memberships when an account closes or is exported (step 8).
        from . import lifecycle
        lifecycle.register()
