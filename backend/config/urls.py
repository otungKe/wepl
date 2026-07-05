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


def health_live(request):
    """Liveness: the process is up and serving. No dependency checks (ADR-0020).
    Use this for the container/orchestrator liveness probe — a failing dependency
    must not cause the pod to be killed and restarted in a loop."""
    return JsonResponse({'status': 'ok'})


def health_ready(request):
    """Readiness: can this instance serve traffic? Checks DB + cache (ADR-0020).
    Use this for the readiness probe / load-balancer — a failed dependency takes
    the instance out of rotation without restarting it."""
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
    # Health probes (ADR-0020). /health/ kept as an alias of readiness for the
    # existing uptime monitor.
    path('health/',       health_ready, name='health'),
    path('health/live/',  health_live,  name='health-live'),
    path('health/ready/', health_ready, name='health-ready'),
    path('admin/', admin.site.urls),

    # API (P1 #6). The same map is served at the legacy unversioned prefix that
    # existing mobile binaries call, and at the versioned /api/v1/ space new
    # clients should target. See config/api_urls.py.
    path('api/',    include('config.api_urls')),
    path('api/v1/', include('config.api_urls')),
    # /api/v2/ carries only endpoints whose contract deliberately breaks v1
    # (e.g. the cursor-paginated activity feed). See config/api_v2_urls.py + ADR-0021.
    path('api/v2/', include('config.api_v2_urls')),

    # Back Office operations console (staff-only, RBAC-enforced). Versionless —
    # an internal surface, not a public client contract. See apps/backoffice.
    path('api/ops/', include('apps.backoffice.urls')),

    # OpenAPI schema + interactive docs (drf-spectacular).
    path('api/schema/',             SpectacularAPIView.as_view(), name='schema'),
    path('api/schema/swagger-ui/',  SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/schema/redoc/',       SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]
