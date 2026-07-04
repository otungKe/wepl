import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    queue='notifications',
)
def send_notification(
    self,
    user_id,
    notification_type,
    title,
    message,
    community_id=None,
    conversation_id=None,
    contribution_id=None,
    join_request_id=None,
    event_id=None,
):
    """
    Create a Notification record and dispatch an FCM push notification to all
    of the user's registered devices.

    Retries up to 3 times on transient failure with 30-second backoff.
    ``event_id`` (outbox id) is passed through for idempotent creation.
    """
    from .models import NotificationPreferences
    from .channels import CHANNELS, channels_for

    payload = {
        'user_id': user_id,
        'notification_type': notification_type,
        'title': title,
        'message': message,
        'community_id': community_id,
        'conversation_id': conversation_id,
        'contribution_id': contribution_id,
        'join_request_id': join_request_id,
        'event_id': event_id,
    }

    prefs, _ = NotificationPreferences.objects.get_or_create(user_id=user_id)
    keys = channels_for(notification_type, prefs)
    if not keys:
        logger.debug(
            "send_notification: suppressed %s for user %s (preferences)",
            notification_type, user_id,
        )
        return

    # Per-community mute — drop push (keep the in-app record) when the recipient
    # has muted this community's activity.
    if community_id and 'push' in keys:
        from apps.communities.models import CommunityMembership
        if CommunityMembership.objects.filter(
            community_id=community_id, user_id=user_id,
            is_active=True, notifications_muted=True,
        ).exists():
            keys = [k for k in keys if k != 'push']

    # The in-app row is the durable record — retry it (idempotent via event_id),
    # and dead-letter only once retries are exhausted so it is never lost.
    if 'in_app' in keys:
        try:
            CHANNELS['in_app'].deliver(payload)
        except Exception as exc:
            try:
                raise self.retry(exc=exc)
            except self.MaxRetriesExceededError:
                from .deadletter import record
                record(channel='in_app', payload=payload, error=str(exc))
                return

    # Other channels are best-effort; the push task self-dead-letters on failure.
    for key in keys:
        if key == 'in_app':
            continue
        try:
            CHANNELS[key].deliver(payload)
        except Exception as exc:  # enqueue failure (rare) — don't lose it
            from .deadletter import record
            record(channel=key, payload=payload, error=str(exc))


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=15,
    queue='notifications',
    ignore_result=True,
)
def _push_to_devices(self, user_id, title, body, data=None):
    """
    Send an FCM push notification to every device the user has registered.

    Stale / invalid tokens return a 404 (UNREGISTERED) from FCM — we delete
    them silently so the token list self-heals over time.
    """
    from .models import UserDevice

    tokens = list(
        UserDevice.objects.filter(user_id=user_id).values_list('fcm_token', flat=True)
    )
    if not tokens:
        return

    try:
        import firebase_admin
        from firebase_admin import messaging
        from firebase_admin.exceptions import FirebaseError

        # Initialise the SDK once per worker process using GOOGLE_APPLICATION_CREDENTIALS
        # or the FIREBASE_CREDENTIALS_JSON Django setting (path to a service-account JSON).
        if not firebase_admin._apps:
            from django.conf import settings
            import json, os

            cred_path = getattr(settings, 'FIREBASE_CREDENTIALS_JSON', None)
            if cred_path and os.path.exists(cred_path):
                cred = firebase_admin.credentials.Certificate(cred_path)
            else:
                # Falls back to GOOGLE_APPLICATION_CREDENTIALS env var
                cred = firebase_admin.credentials.ApplicationDefault()
            firebase_admin.initialize_app(cred)

        messages = [
            messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                data={k: v for k, v in (data or {}).items() if v},
                token=token,
                android=messaging.AndroidConfig(priority='high'),
                apns=messaging.APNSConfig(
                    payload=messaging.APNSPayload(
                        aps=messaging.Aps(sound='default'),
                    ),
                ),
            )
            for token in tokens
        ]

        response = messaging.send_each(messages)

        # Prune unregistered tokens
        stale = [
            tokens[i]
            for i, r in enumerate(response.responses)
            if not r.success and (
                r.exception and 'UNREGISTERED' in str(r.exception)
            )
        ]
        if stale:
            UserDevice.objects.filter(fcm_token__in=stale).delete()
            logger.info("FCM: removed %d stale token(s) for user %s", len(stale), user_id)

        logger.info(
            "FCM push for user %s: %d success / %d failure",
            user_id, response.success_count, response.failure_count,
        )

    except ImportError:
        logger.warning("firebase-admin not installed — FCM push skipped.")
    except Exception as exc:
        logger.exception("FCM push failed for user %s: %s", user_id, exc)
        if self.request.retries >= self.max_retries:
            # Retries exhausted — record instead of dropping the push (ADR-0015).
            from .deadletter import record
            record(
                channel='push',
                user_id=user_id,
                notification_type=(data or {}).get('type', ''),
                payload={'user_id': user_id, 'title': title, 'body': body, 'data': data or {}},
                error=str(exc),
            )
            return
        raise self.retry(exc=exc)
