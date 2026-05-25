from django.conf import settings
from django.db import models


class Activity(models.Model):
    ACTIVITY_TYPES = (
        ('community_created', 'Community Created'),
        ('community_joined', 'Community Joined'),
        ('community_left', 'Community Left'),
        ('conversation_created', 'Conversation Created'),
        ('message_sent', 'Message Sent'),
        ('contribution_created', 'Contribution Created'),
        ('contribution_payment', 'Contribution Payment'),
        ('standing_order_executed', 'Standing Order Executed'),
        ('welfare_contribution', 'Welfare Contribution'),
        ('payment_made', 'Payment Made'),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )

    activity_type = models.CharField(
        max_length=50,
        choices=ACTIVITY_TYPES
    )

    message = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at'], name='activity_user_date_idx'),
        ]

    def __str__(self):
        return self.message
