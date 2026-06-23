from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from django.db import connection
from django.core.cache import cache

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)


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

    # API (P1 #6). The same map is served at the legacy unversioned prefix that
    # existing mobile binaries call, and at the versioned /api/v1/ space new
    # clients should target. See config/api_urls.py.
    path('api/',    include('config.api_urls')),
    path('api/v1/', include('config.api_urls')),

    # OpenAPI schema + interactive docs (drf-spectacular).
    path('api/schema/',             SpectacularAPIView.as_view(), name='schema'),
    path('api/schema/swagger-ui/',  SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/schema/redoc/',       SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]
