from django.apps import AppConfig


class TenantsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.tenants'

    def ready(self):
        # Clear RLS tenant context at Celery task boundaries (P6-04 follow-up).
        from . import celery_hooks
        celery_hooks.connect()
        # Pin the RLS tenant during authentication, without the auth layer
        # having to know what a tenant is (ADR-0033).
        from . import auth
        auth.register()
