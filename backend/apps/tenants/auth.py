"""Tenant-aware JWT authentication (Phase 6, P6-04).

The app authenticates with JWT inside DRF (not Django's session middleware), so
the per-request RLS tenant context is set here — right after the user is resolved,
before the view's DB queries run. ``TenantRLSMiddleware`` resets it afterwards.

Platform operators (staff / superusers) are deliberately NOT pinned to a tenant:
they work across tenants (e.g. the staff reports API with ?tenant_id=), and the
Django admin must stay platform-wide. Regular members are pinned to their tenant,
so RLS restricts their connection to their own rows.
"""
from rest_framework_simplejwt.authentication import JWTAuthentication

from .resolve import tenant_for_user
from .rls import set_current_tenant


class TenantJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        result = super().authenticate(request)
        if result is not None:
            user, _token = result
            if user and user.is_authenticated and not (user.is_staff or user.is_superuser):
                set_current_tenant(tenant_for_user(user).id)
        return result
