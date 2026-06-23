"""Dead-letter recording for failed notification deliveries (ADR-0015)."""
import logging

logger = logging.getLogger(__name__)


def record(*, channel: str, payload: dict, error: str = "",
           user_id=None, notification_type: str = ""):
    """Persist a failed delivery so it isn't lost. Best-effort — recording a
    dead-letter must never itself raise into the delivery path."""
    from .models import NotificationDeadLetter
    try:
        return NotificationDeadLetter.objects.create(
            user_id=user_id or payload.get("user_id"),
            notification_type=notification_type or payload.get("notification_type", ""),
            channel=channel,
            payload=payload or {},
            error=(error or "")[:5000],
        )
    except Exception:  # pragma: no cover - last-resort safety
        logger.exception("Failed to record notification dead-letter (channel=%s)", channel)
        return None
