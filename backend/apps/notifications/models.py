from django.conf import settings
from django.db import models


class Notification(models.Model):

    NOTIFICATION_TYPES = (
        ('community_join',          'Community Join'),
        ('conversation_created',    'Conversation Created'),
        ('new_message',             'New Message'),
        ('contribution_payment',    'Contribution Payment'),
        ('payment_recorded',        'Payment Recorded'),
        ('contribution_milestone',  'Contribution Milestone'),
        ('contribution_joined',     'Contribution Joined'),
        # ROSCA
        ('rosca_rotation_set',      'ROSCA Rotation Set'),
        ('rosca_payout',            'ROSCA Payout'),
        # Disbursement
        ('disbursement_requested',  'Disbursement Requested'),
        ('disbursement_rejected',   'Disbursement Rejected'),
        ('disbursement_executed',   'Disbursement Executed'),
        # Welfare
        ('welfare_claim',           'Welfare Claim'),
        ('welfare_rejected',        'Welfare Rejected'),
        ('welfare_disbursed',       'Welfare Disbursed'),
        # Advances
        ('advance_requested',       'Advance Requested'),
        ('advance_approved',        'Advance Approved'),
        ('advance_rejected',        'Advance Rejected'),
        ('advance_sent',            'Advance Sent'),
        # B2C payout confirmations
        ('disbursement_sent',       'Disbursement Sent'),
        # Community join requests
        ('join_request',            'Join Request'),
        ('join_approved',           'Join Approved'),
        ('join_rejected',           'Join Rejected'),
        # Contribution join requests & invitations
        ('contribution_join_request',   'Contribution Join Request'),
        ('contribution_invite',         'Contribution Invite'),
        ('contribution_join_approved',  'Contribution Join Approved'),
        ('contribution_join_rejected',  'Contribution Join Rejected'),
        ('contribution_invite_accepted','Contribution Invite Accepted'),
        # Amendments
        ('amendment_proposed',      'Amendment Proposed'),
        ('amendment_approved',      'Amendment Approved'),
        ('amendment_rejected',      'Amendment Rejected'),
        # Reminders
        ('reminder',                'Reminder'),
        # ROSCA payout confirmed (B2C callback received)
        ('rosca_payout_confirmed',  'ROSCA Payout Confirmed'),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications'
    )

    notification_type = models.CharField(
        max_length=50,
        choices=NOTIFICATION_TYPES
    )

    title = models.CharField(max_length=255)
    message = models.TextField()
    is_read = models.BooleanField(default=False)

    community_id = models.IntegerField(null=True, blank=True)
    conversation_id = models.IntegerField(null=True, blank=True)
    contribution_id = models.IntegerField(null=True, blank=True)
    join_request_id = models.IntegerField(null=True, blank=True)

    # Outbox idempotency: the OutboxEvent id this notification was created from.
    # Unique so at-least-once relay redelivery is a no-op (NULL for direct creates).
    event_id = models.BigIntegerField(null=True, blank=True, unique=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read', '-created_at'], name='notif_user_read_date_idx'),
            models.Index(fields=['user', 'is_read'],                name='notif_user_read_idx'),
        ]

    def __str__(self):
        return f"[{self.notification_type}] {self.user.phone_number}: {self.title}"


class NotificationPreferences(models.Model):
    """
    Per-user notification preference flags.

    One row per user, auto-created on first access.
    All flags default to True (opt-in for everything).

    The send_notification Celery task checks these flags before creating a
    Notification record or dispatching an FCM push — so toggling a category
    OFF means the user genuinely receives nothing for that category.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notification_prefs',
    )
    # Master switch — if False, suppress ALL notifications.
    push_enabled  = models.BooleanField(default=True)

    # Category switches
    payments      = models.BooleanField(default=True)  # payments & M-Pesa
    contributions = models.BooleanField(default=True)  # contributions & governance
    reminders     = models.BooleanField(default=True)  # scheduled reminders
    communities   = models.BooleanField(default=True)  # community & chat activity
    advances      = models.BooleanField(default=True)  # advances & welfare
    # Security & sign-in alerts (new device, PIN change). Mandatory — the UI
    # surfaces these as always-on and never lets them be turned off.
    security      = models.BooleanField(default=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"NotifPrefs({self.user.phone_number})"


# Maps each notification_type to one of the category fields above.
# Types NOT in this map always pass through (e.g. system / admin messages).
NOTIF_CATEGORY_MAP: dict[str, str] = {
    # Payments & M-Pesa
    'contribution_payment':      'payments',
    'payment_recorded':          'payments',
    'disbursement_sent':         'payments',
    'advance_sent':              'payments',
    'rosca_payout':              'payments',
    'rosca_payout_confirmed':    'payments',
    'welfare_disbursed':         'payments',
    # Contributions & governance
    'contribution_joined':       'contributions',
    'contribution_milestone':    'contributions',
    'rosca_rotation_set':        'contributions',
    'disbursement_requested':    'contributions',
    'disbursement_rejected':     'contributions',
    'disbursement_executed':     'contributions',
    'amendment_proposed':        'contributions',
    'amendment_approved':        'contributions',
    'amendment_rejected':        'contributions',
    'contribution_join_request': 'contributions',
    'contribution_invite':       'contributions',
    'contribution_join_approved':'contributions',
    'contribution_join_rejected':'contributions',
    'contribution_invite_accepted':'contributions',
    # Reminders
    'reminder':                  'reminders',
    # Community & chat
    'community_join':            'communities',
    'join_request':              'communities',
    'join_approved':             'communities',
    'join_rejected':             'communities',
    'conversation_created':      'communities',
    'new_message':               'communities',
    # Advances & welfare
    'advance_requested':         'advances',
    'advance_approved':          'advances',
    'advance_rejected':          'advances',
    'welfare_claim':             'advances',
    'welfare_rejected':          'advances',
    # Security & sign-in (mandatory category — the pref defaults True and the
    # client never lets it be disabled).
    'security_new_signin':       'security',
    'security_pin_changed':      'security',
}


class UserDevice(models.Model):
    """
    Stores FCM registration tokens so the backend can send push notifications
    to specific devices (Issue 19).

    One user may have multiple devices (e.g. phone + tablet).
    Tokens are upserted on every app launch via POST /notifications/devices/.
    Stale tokens are silently discarded by the FCM task after a 404 response.
    """

    PLATFORM_CHOICES = (
        ('android', 'Android'),
        ('ios',     'iOS'),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='devices',
    )
    fcm_token = models.TextField(unique=True)
    platform  = models.CharField(max_length=10, choices=PLATFORM_CHOICES, default='android')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['user'], name='device_user_idx'),
        ]

    def __str__(self):
        return f"{self.user.phone_number} [{self.platform}]"


class NotificationDeadLetter(models.Model):
    """A notification delivery that failed on a channel after retries (ADR-0015).

    At-least-once delivery means transient failures get retried; when retries are
    exhausted the attempt is recorded here instead of being lost, so it is
    queryable and replayable by ops rather than silently dropped.
    """
    user_id           = models.BigIntegerField(null=True, blank=True)
    notification_type = models.CharField(max_length=50, blank=True, default="")
    channel           = models.CharField(max_length=20, db_index=True)
    payload           = models.JSONField(default=dict, blank=True)
    error             = models.TextField(blank=True, default="")
    created_at        = models.DateTimeField(auto_now_add=True, db_index=True)
    resolved_at       = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["channel", "-created_at"], name="notif_dlq_channel_idx"),
        ]

    def __str__(self):
        state = "resolved" if self.resolved_at else "pending"
        return f"DLQ[{self.channel}] {self.notification_type} user={self.user_id} ({state})"
