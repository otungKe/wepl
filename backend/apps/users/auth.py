"""
Staged-JWT authentication and authorization.

The auth flow issues tokens in three stages, carried in a ``stage`` claim:

    otp_verified  — phone proven, new/unfinished user. May ONLY set a PIN.
    otp_recovery  — phone proven, existing user resetting a forgotten PIN.
                    May ONLY reset a PIN.
    active        — full session. Required for every money/data endpoint.

CRITICAL: the project's DEFAULT permission must be ``IsActiveSession`` so that
intermediate (otp_verified / otp_recovery) tokens cannot reach contribution,
disbursement or M-Pesa endpoints. The two PIN endpoints opt into the narrower
``StageRequired`` permission. See settings note in this app's README.
"""
import logging

from rest_framework.permissions import BasePermission
from rest_framework_simplejwt.tokens import RefreshToken

logger = logging.getLogger(__name__)

# ── Stage constants ────────────────────────────────────────────────────────────

STAGE_OTP_VERIFIED = "otp_verified"
STAGE_OTP_RECOVERY = "otp_recovery"
STAGE_ACTIVE       = "active"

STAGE_CLAIM = "stage"


def issue_tokens(user, stage: str) -> dict:
    """
    Mint a refresh/access pair tagged with the given auth stage.
    Returns a dict ready to merge into a Response body::

        return Response({"message": "OK", **issue_tokens(user, STAGE_ACTIVE)})
    """
    refresh = RefreshToken.for_user(user)
    refresh[STAGE_CLAIM] = stage
    logger.debug("Issued %s token for user %s", stage, user.phone_number)
    return {
        "access":  str(refresh.access_token),
        "refresh": str(refresh),
    }


def _token_stage(request) -> str | None:
    """Extract the stage claim from the validated token attached to *request*."""
    auth = getattr(request, "auth", None)
    if auth is None:
        return None
    # simplejwt tokens expose .payload; be defensive for other token types.
    payload = getattr(auth, "payload", None)
    if isinstance(payload, dict):
        return payload.get(STAGE_CLAIM)
    return None


# ── Permissions ────────────────────────────────────────────────────────────────

class IsActiveSession(BasePermission):
    """
    Default permission for the whole API.

    Authenticated AND holding an 'active'-stage token. Intermediate OTP tokens
    (otp_verified / otp_recovery) are rejected here — they can only reach the
    PIN endpoints that explicitly opt into StageRequired.
    """
    message = "A completed login (active session) is required."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        return _token_stage(request) == STAGE_ACTIVE


class StageRequired(BasePermission):
    """
    Allow only tokens whose stage is in ``view.required_stages``.

    Usage on a view::

        permission_classes = [StageRequired]
        required_stages    = {STAGE_OTP_VERIFIED}
    """
    message = "This action requires a different authentication stage."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        allowed = getattr(view, "required_stages", set())
        return _token_stage(request) in allowed
