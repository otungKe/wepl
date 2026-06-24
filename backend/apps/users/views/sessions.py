from ._common import *  # shared imports/helpers (ADR-0013 view split)


def _current_sid(request):
    """The sid claim of the token authenticating this request, if any."""
    from ..sessions import SID_CLAIM
    auth = getattr(request, "auth", None)
    payload = getattr(auth, "payload", None)
    if isinstance(payload, dict):
        return payload.get(SID_CLAIM)
    return None


class LogoutView(APIView):
    """POST /auth/logout/ — end the current session.

    Body: {"refresh": "<refresh token>"} (optional but recommended). Blacklists the
    refresh token and revokes the current session so its access tokens stop working.
    """
    permission_classes = [IsActiveSession]

    def post(self, request):
        from rest_framework_simplejwt.tokens import RefreshToken
        from ..sessions import active_session, revoke

        refresh = (request.data.get("refresh") or "").strip()
        if refresh:
            try:
                RefreshToken(refresh).blacklist()
            except Exception:
                pass  # already expired/blacklisted — logout is idempotent

        sid = _current_sid(request)
        if sid:
            session = active_session(sid)
            if session:
                revoke(session)
        logger.info("Logout: user %s ended session %s", request.user.id, sid)
        return Response({"message": "Logged out."}, status=status.HTTP_200_OK)


class SessionListView(APIView):
    """GET /auth/sessions/ — list this user's active sessions (current flagged)."""
    permission_classes = [IsActiveSession]

    def get(self, request):
        from ..models import UserSession
        from ..serializers import UserSessionSerializer

        current = _current_sid(request)
        sessions = UserSession.objects.filter(user=request.user, revoked_at__isnull=True)
        data = UserSessionSerializer(
            sessions, many=True, context={"current_sid": str(current) if current else None},
        ).data
        return Response(data)


class SessionRevokeView(APIView):
    """POST /auth/sessions/<sid>/revoke/ — revoke one of this user's sessions."""
    permission_classes = [IsActiveSession]

    def post(self, request, sid):
        from ..models import UserSession
        from ..sessions import revoke

        session = UserSession.objects.filter(
            sid=sid, user=request.user, revoked_at__isnull=True,
        ).first()
        if not session:
            return Response({"error": "Session not found."}, status=status.HTTP_404_NOT_FOUND)
        revoke(session)
        return Response({"message": "Session revoked."}, status=status.HTTP_200_OK)


class SessionRevokeOthersView(APIView):
    """POST /auth/sessions/revoke-others/ — log out everywhere except this device."""
    permission_classes = [IsActiveSession]

    def post(self, request):
        from ..sessions import revoke_all_for_user

        current = _current_sid(request)
        count = revoke_all_for_user(request.user, except_sid=current)
        return Response({"message": f"Revoked {count} other session(s).", "revoked": count})


# -----------------------------
# 6. USER PROFILE
# -----------------------------
