from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'
    verbose_name = 'Core'

    def ready(self):
        # Heartbeat: stamp each watched beat task's liveness on completion (OP-2).
        from celery.signals import task_postrun

        from . import health

        @task_postrun.connect(weak=False)
        def _stamp_heartbeat(sender=None, task=None, **kwargs):
            name = getattr(task, "name", None) or getattr(sender, "name", None)
            if name in health.WATCHED_TASKS:
                try:
                    health.stamp(name)
                except Exception:  # never let telemetry break task execution
                    pass
