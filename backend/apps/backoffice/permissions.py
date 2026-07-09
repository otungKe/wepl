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
    """Require a fresh step-up (TOTP) proof on sensitive ops actions.

    The operator's shift JWT proves identity for the whole shift; this
    additionally requires an ``X-Ops-StepUp`` elevation token — minted by
    ``/api/ops/auth/step-up/`` only after a live TOTP/recovery code is verified,
    and valid for a few minutes (see ``stepup.py``, OP-3). Superusers are *not*
    exempt: the break-glass account is the highest-value credential and must step
    up too. Compose after ``RequireCapability`` so a missing capability surfaces
    its own message first."""
    message = "This action requires step-up authentication."

    def has_permission(self, request, view):
        if getattr(request, "ops_stepped_up", False):
            return True
        from .models import StaffAccount
        from .stepup import STEPUP_HEADER, stepup_token_valid

        user = getattr(request, "user", None)
        if not isinstance(user, StaffAccount):
            return False
        token = request.META.get(STEPUP_HEADER, "")
        if stepup_token_valid(token, user):
            request.ops_stepped_up = True
            return True
        return False
