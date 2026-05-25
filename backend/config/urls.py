from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from django.db import connection
from django.core.cache import cache


def health_check(request):
    """Lightweight health endpoint for uptime monitors and container probes."""
    checks = {}
    try:
        connection.ensure_connection()
        checks['db'] = 'ok'
    except Exception:
        checks['db'] = 'error'

    try:
        cache.set('_health', 1, timeout=5)
        checks['cache'] = 'ok'
    except Exception:
        checks['cache'] = 'error'

    ok = all(v == 'ok' for v in checks.values())
    return JsonResponse({'status': 'ok' if ok else 'degraded', **checks},
                        status=200 if ok else 503)


urlpatterns = [
    path('health/', health_check, name='health'),
    path('admin/', admin.site.urls),
    path('api/users/', include('apps.users.urls')),
    path('api/communities/', include('apps.communities.urls')),
    path('api/conversations/', include('apps.conversations.urls')),
    path('api/contributions/', include('apps.contributions.urls')),
    path('api/payments/', include('apps.payments.urls')),
    path('api/activity/', include('apps.activity.urls')),
    path('api/notifications/', include('apps.notifications.urls')),
    path('api/mpesa/',     include('apps.mpesa.urls')),
    path('api/reminders/', include('apps.reminders.urls')),
]
