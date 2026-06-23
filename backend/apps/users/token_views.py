"""Session-aware token refresh (ADR-0010).

Kept in its own module (not ``auth.py``) because importing SimpleJWT's *views*
pulls in DRF generics, and ``auth.py`` sits in the DEFAULT_AUTHENTICATION_CLASSES
import chain — importing views there would re-enter that resolution and deadlock.
Only ``urls.py`` imports this module.
"""
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView


class SessionTokenRefreshSerializer(TokenRefreshSerializer):
    """Refuse to refresh a token whose session has been revoked (ADR-0010)."""

    def validate(self, attrs):
        from .sessions import SID_CLAIM, active_session, touch
        sid = RefreshToken(attrs["refresh"]).payload.get(SID_CLAIM)
        session = active_session(sid) if sid else None
        if sid and session is None:
            raise InvalidToken("This session has been revoked. Please sign in again.")
        data = super().validate(attrs)   # rotates/blacklists; sid survives onto the new token
        if session is not None:
            touch(session)
        return data


class SessionTokenRefreshView(TokenRefreshView):
    serializer_class = SessionTokenRefreshSerializer
