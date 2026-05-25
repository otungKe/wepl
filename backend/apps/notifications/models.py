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

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read', '-created_at'], name='notif_user_read_date_idx'),
            models.Index(fields=['user', 'is_read'],                name='notif_user_read_idx'),
        ]

    def __str__(self):
        return f"[{self.notification_type}] {self.user.phone_number}: {self.title}"
