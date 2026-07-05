"""DRF permissions for the Back Office. All enforcement is server-side."""
from __future__ import annotations

from rest_framework.permissions import BasePermission

from .capabilities import has_capability, is_operator


class IsOperator(BasePermission):
    """Authenticated staff member who belongs to at least one ops role."""
    message = "Back Office access requires an operations role."

    def has_permission(self, request, view):
        return is_operator(request.user)


def RequireCapability(capability: str):
    """Permission-class factory: gate a view on a single ops capability.

    Usage::

        permission_classes = [RequireCapability("verification.decide")]
    """
    class _RequireCapability(BasePermission):
        message = f"Missing required capability: {capability}."

        def has_permission(self, request, view):
            return has_capability(request.user, capability)

    _RequireCapability.__name__ = f"RequireCapability_{capability.replace('.', '_')}"
    return _RequireCapability


class RequireStepUp(BasePermission):
    """Placeholder for step-up (re-auth) on sensitive ops actions.

    P0 wires the hook; the enforced re-auth flow lands with the first sensitive
    action module. A request is considered stepped-up if the middleware/session
    marked it within the recent window. Until that ships, this is permissive for
    superusers only so it can be attached to endpoints without blocking P0.
    """
    message = "This action requires step-up authentication."

    def has_permission(self, request, view):
        if getattr(request, "ops_stepped_up", False):
            return True
        # Conservative default until the step-up flow ships.
        return bool(request.user and request.user.is_superuser)
