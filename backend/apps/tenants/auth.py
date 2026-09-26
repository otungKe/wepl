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

Every customer ``User`` is pinned, including one with ``is_staff`` or
``is_superuser``: those flags grant Django-admin access, not a cross-tenant view
of the API. Django admin itself is not a DRF view, so it never reaches this hook
and stays platform-wide. Operators who work across tenants do so in the ops
console as ``StaffAccount``s, which authenticate separately and are not pinned
here.
"""
from .resolve import tenant_for_user
from .rls import set_current_tenant


def pin_request_tenant(*, user, request=None) -> None:
    """Pin the connection's ``app.tenant_id`` GUC to *user*'s tenant."""
    if user and user.is_authenticated:
        tenant_id = tenant_for_user(user).id
        set_current_tenant(tenant_id)
        from apps.core.observability import bind
        bind(tenant_id=tenant_id)


def register() -> None:
    """Subscribe to authentication. Called from ``TenantsConfig.ready()``."""
    from apps.core.request_context import register_post_authenticate
    register_post_authenticate(pin_request_tenant)
