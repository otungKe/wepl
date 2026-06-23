"""Session registry helpers (ADR-0010).

Pure functions over ``UserSession`` so views, the auth class and the refresh view
share one implementation. The ``sid`` claim on the JWT is the link between a token
and its session row.
"""
import logging
from datetime import timedelta

from django.utils import timezone

from .models import UserSession

logger = logging.getLogger(__name__)

SID_CLAIM = "sid"

# Only write last_seen_at when it is older than this, to avoid a DB write per request.
_TOUCH_EVERY = timedelta(seconds=60)


def _client_ip(request) -> str | None:
    if request is None:
        return None
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or None


def _device_label(request) -> str:
    """Best-effort human label from the client. The mobile app may send an explicit
    X-Device-Name header; otherwise fall back to a trimmed user-agent."""
    if request is None:
        return ""
    explicit = request.META.get("HTTP_X_DEVICE_NAME", "").strip()
    if explicit:
        return explicit[:120]
    return request.META.get("HTTP_USER_AGENT", "").strip()[:120]


def create_session(user, request=None) -> UserSession:
    """Create a session row and return it; its ``sid`` goes into the token."""
    session = UserSession.objects.create(
        user=user,
        device_label=_device_label(request),
        user_agent=(request.META.get("HTTP_USER_AGENT", "")[:400] if request else ""),
        ip_address=_client_ip(request),
    )
    logger.info("Session created for user %s (sid=%s)", user.id, session.sid)
    return session


def active_session(sid) -> UserSession | None:
    """Return the non-revoked session for *sid*, or None."""
    if not sid:
        return None
    return UserSession.objects.filter(sid=sid, revoked_at__isnull=True).first()


def touch(session: UserSession) -> None:
    """Throttled update of last_seen_at (best-effort; never raises)."""
    try:
        now = timezone.now()
        if now - session.last_seen_at >= _TOUCH_EVERY:
            UserSession.objects.filter(pk=session.pk).update(last_seen_at=now)
    except Exception:  # pragma: no cover - telemetry only, must never break auth
        logger.debug("touch() failed for session %s", getattr(session, "pk", "?"))


def revoke(session: UserSession) -> None:
    if session.revoked_at is None:
        session.revoked_at = timezone.now()
        session.save(update_fields=["revoked_at"])
        logger.info("Session revoked (sid=%s, user=%s)", session.sid, session.user_id)


def revoke_all_for_user(user, *, except_sid=None) -> int:
    """Revoke every active session for *user* (optionally keeping one). Also
    best-effort blacklists outstanding refresh tokens. Returns count revoked."""
    qs = UserSession.objects.filter(user=user, revoked_at__isnull=True)
    if except_sid:
        qs = qs.exclude(sid=except_sid)
    count = qs.update(revoked_at=timezone.now())
    if count and except_sid is None:
        blacklist_outstanding(user)
    logger.info("Revoked %d session(s) for user %s", count, user.id)
    return count


def blacklist_outstanding(user) -> None:
    """Best-effort: blacklist all of *user*'s outstanding refresh tokens.

    The session check is the source of truth for revocation; this is defence in
    depth so a stolen refresh token can't be replayed even out of band.
    """
    try:
        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
        from rest_framework_simplejwt.tokens import RefreshToken
        for ot in OutstandingToken.objects.filter(user=user):
            try:
                RefreshToken(ot.token).blacklist()
            except Exception:
                pass
    except Exception:  # pragma: no cover
        logger.debug("blacklist_outstanding failed for user %s", user.id)
