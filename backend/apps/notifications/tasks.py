import logging

from celery import shared_task

from .services import NotificationService

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
):
    """
    Create a Notification record and dispatch an FCM push notification to all
    of the user's registered devices.

    Retries up to 3 times on transient failure with 30-second backoff.
    """
    try:
        # ── Check user's notification preferences ─────────────────────────────
        from .models import NotificationPreferences, NOTIF_CATEGORY_MAP
        prefs, _ = NotificationPreferences.objects.get_or_create(user_id=user_id)

        if not prefs.push_enabled:
            logger.debug(
                "send_notification: suppressed %s for user %s — push disabled",
                notification_type, user_id,
            )
            return

        category = NOTIF_CATEGORY_MAP.get(notification_type)
        if category and not getattr(prefs, category, True):
            logger.debug(
                "send_notification: suppressed %s for user %s — category '%s' disabled",
                notification_type, user_id, category,
            )
            return

        NotificationService.create(
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            message=message,
            community_id=community_id,
            conversation_id=conversation_id,
            contribution_id=contribution_id,
            join_request_id=join_request_id,
        )
        # Best-effort push — failure here must not retry the DB write above.
        _push_to_devices.delay(
            user_id=user_id,
            title=title,
            body=message,
            data={
                'type':            notification_type,
                'community_id':    str(community_id    or ''),
                'contribution_id': str(contribution_id or ''),
                'conversation_id': str(conversation_id or ''),
            },
        )
    except Exception as exc:
        raise self.retry(exc=exc)


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
        raise self.retry(exc=exc)
