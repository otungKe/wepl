"""Notification channel strategy + preference routing (ADR-0015).

Delivery used to be hardcoded in the Celery task: create the in-app row, then fire
FCM. Adding a channel meant editing the task. This makes each delivery surface a
pluggable ``NotificationChannel`` and turns "which channels does this notification
go to" into a single routing function driven by the user's preferences.

Adding email/SMS/WhatsApp later = implement a channel + register it + (optionally)
add a preference flag to the routing matrix. No task edits.
"""
import abc

from .models import NOTIF_CATEGORY_MAP


class NotificationChannel(abc.ABC):
    """A delivery surface. ``deliver`` raises on failure so the caller can retry
    / dead-letter; it must be idempotent where the medium allows (the in-app
    channel dedupes on the outbox event id)."""

    key: str = ""

    @abc.abstractmethod
    def deliver(self, payload: dict) -> None:  # pragma: no cover - interface
        ...


class InAppChannel(NotificationChannel):
    """The durable in-app inbox row. Idempotent via Notification.event_id."""
    key = "in_app"

    def deliver(self, payload: dict) -> None:
        from .services import NotificationService
        NotificationService.create(
            user_id=payload["user_id"],
            notification_type=payload["notification_type"],
            title=payload["title"],
            message=payload["message"],
            community_id=payload.get("community_id"),
            conversation_id=payload.get("conversation_id"),
            contribution_id=payload.get("contribution_id"),
            join_request_id=payload.get("join_request_id"),
            event_id=payload.get("event_id"),
        )


class PushChannel(NotificationChannel):
    """FCM push to the user's registered devices (dispatched async, best-effort —
    the push task self-dead-letters on terminal failure)."""
    key = "push"

    def deliver(self, payload: dict) -> None:
        from .tasks import _push_to_devices
        _push_to_devices.delay(
            user_id=payload["user_id"],
            title=payload["title"],
            body=payload["message"],
            data={
                "type":            payload["notification_type"],
                "community_id":    str(payload.get("community_id") or ""),
                "contribution_id": str(payload.get("contribution_id") or ""),
                "conversation_id": str(payload.get("conversation_id") or ""),
            },
        )


# Registry. Email/SMS/WhatsApp channels register here once implemented.
CHANNELS: dict[str, NotificationChannel] = {
    c.key: c for c in (InAppChannel(), PushChannel())
}


def channels_for(notification_type: str, prefs) -> list[str]:
    """The ordered channel keys a notification should be delivered through, given
    the user's preferences. Empty list = suppressed.

    Preserves today's behaviour: ``push_enabled`` is the master switch, and a
    disabled category suppresses the type. Per-channel opt-outs (email/sms) are a
    documented follow-up (needs new preference fields).
    """
    if not prefs.push_enabled:
        return []
    category = NOTIF_CATEGORY_MAP.get(notification_type)
    if category and not getattr(prefs, category, True):
        return []
    return ["in_app", "push"]
