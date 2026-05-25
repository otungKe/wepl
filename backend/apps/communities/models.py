import uuid

from django.conf import settings
from django.db import models


def _generate_invite_code():
    return uuid.uuid4().hex[:10].upper()


class Community(models.Model):

    CATEGORY_CHOICES = (
        ('savings',    'Savings'),
        ('chama',      'Chama / Investment Club'),
        ('investment', 'Investment'),
        ('welfare',    'Welfare'),
        ('emergency',  'Emergency Fund'),
        ('business',   'Business'),
        ('general',    'General'),
    )

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_communities'
    )

    community_photo = models.ImageField(
        upload_to='communities/',
        null=True, blank=True
    )

    is_private       = models.BooleanField(default=False)
    invite_code      = models.CharField(max_length=20, unique=True, default=_generate_invite_code)
    has_welfare_fund = models.BooleanField(default=False)
    has_shares_fund  = models.BooleanField(default=False)
    category         = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='general')
    location         = models.CharField(max_length=120, blank=True, default='')
    created_at       = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class CommunityMembership(models.Model):

    ROLE_CHOICES = (
        ('admin',     'Admin'),
        ('treasurer', 'Treasurer'),
        ('member',    'Member'),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    community = models.ForeignKey(Community, on_delete=models.CASCADE, related_name='memberships')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'community')
        indexes = [
            models.Index(fields=['community', 'is_active'], name='mem_community_active_idx'),
            models.Index(fields=['user',      'is_active'], name='mem_user_active_idx'),
        ]

    def __str__(self):
        return f"{self.user.phone_number} - {self.community.name}"


class CommunityJoinRequest(models.Model):

    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
    )

    community = models.ForeignKey(
        Community, on_delete=models.CASCADE, related_name='join_requests'
    )
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='join_requests'
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='reviewed_join_requests'
    )

    class Meta:
        unique_together = ('community', 'requester')
        indexes = [
            models.Index(fields=['community', 'status'], name='joinreq_community_status_idx'),
        ]

    def __str__(self):
        return f"{self.requester.phone_number} → {self.community.name} [{self.status}]"
