"""Requests and invitations to join a contribution."""

from django.conf import settings
from django.db import models

from .contribution import Contribution


class ContributionJoinRequest(models.Model):
    """
    Handles both member-initiated join requests and admin-initiated invitations
    for a contribution. A single row per (contribution, user) pair.
    """
    TYPE_CHOICES = (
        ('REQUEST', 'Join Request'),   # member asked to join
        ('INVITE',  'Invitation'),     # admin/creator invited a member
    )
    STATUS_CHOICES = (
        ('PENDING',   'Pending'),
        ('APPROVED',  'Approved'),
        ('REJECTED',  'Rejected'),
    )

    contribution  = models.ForeignKey(Contribution, on_delete=models.CASCADE, related_name='join_requests')
    user          = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='contribution_join_requests')
    request_type  = models.CharField(max_length=10, choices=TYPE_CHOICES)
    invited_by    = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='contribution_invitations_sent',
    )
    status        = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    created_at    = models.DateTimeField(auto_now_add=True)
    reviewed_at   = models.DateTimeField(null=True, blank=True)
    reviewed_by   = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='contribution_requests_reviewed',
    )

    class Meta:
        unique_together = ('contribution', 'user')

    def __str__(self):
        return f"{self.request_type} — {self.user.phone_number} → {self.contribution.title} [{self.status}]"
