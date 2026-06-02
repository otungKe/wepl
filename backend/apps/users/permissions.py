"""
User-app permissions.

The staged-JWT permissions now live in ``apps.users.auth`` (IsActiveSession,
StageRequired). The classes below are thin, correctly-spelled wrappers kept for
readability at the view layer.

The previous file defined ``IsOTPRecovery`` / ``IsOTPVerfied`` (note the typo)
but inlined ``request.auth.payload.get("stage")`` directly — that was the gap
that let intermediate tokens act as full sessions when the default permission
was not yet ``IsActiveSession``.
"""
from rest_framework.permissions import BasePermission

from .auth import STAGE_OTP_RECOVERY, STAGE_OTP_VERIFIED, _token_stage


class IsOTPVerified(BasePermission):
    """Allow only otp_verified-stage tokens (first-time PIN setup)."""
    message = "A fresh OTP verification is required."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        return _token_stage(request) == STAGE_OTP_VERIFIED


class IsOTPRecovery(BasePermission):
    """Allow only otp_recovery-stage tokens (forgotten-PIN reset)."""
    message = "A fresh OTP verification is required to reset your PIN."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        return _token_stage(request) == STAGE_OTP_RECOVERY
