"""Per-request RLS tenant pinning (Phase 6, P6-04).

The app authenticates with JWT inside DRF (not Django's session middleware), so
the per-request RLS tenant context is set here — right after the user is
resolved, before the view's DB queries run. ``TenantRLSMiddleware`` resets it
afterwards.

This used to be a ``SessionJWTAuthentication`` subclass named in
``DEFAULT_AUTHENTICATION_CLASSES``, which made the tenancy layer import the auth
layer and held both inside the app import cycle. It is now a handler the
authenticator calls (``apps.core.request_context``), registered
from ``TenantsConfig.ready()`` (ADR-0033). It runs at the same moment, in the
same request, and a failure still fails the request — tenancy is not optional, so
a request whose tenant cannot be established must not proceed unscoped.

Platform operators (staff / superusers) are deliberately NOT pinned to a tenant:
they work across tenants (e.g. the staff reports API with ?tenant_id=), and the
Django admin must stay platform-wide. Regular members are pinned to their tenant,
so RLS restricts their connection to their own rows.
"""
from .resolve import tenant_for_user
from .rls import set_current_tenant


def pin_request_tenant(*, user, request=None) -> None:
    """Pin the connection's ``app.tenant_id`` GUC to *user*'s tenant."""
    if user and user.is_authenticated and not (user.is_staff or user.is_superuser):
        tenant_id = tenant_for_user(user).id
        set_current_tenant(tenant_id)
        from apps.core.observability import bind
        bind(tenant_id=tenant_id)


def register() -> None:
    """Subscribe to authentication. Called from ``TenantsConfig.ready()``."""
    from apps.core.request_context import register_post_authenticate
    register_post_authenticate(pin_request_tenant)
