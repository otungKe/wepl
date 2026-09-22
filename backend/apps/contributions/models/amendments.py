"""Proposed changes to a live contribution, and the votes on them."""

from django.conf import settings
from django.db import models

from .contribution import Contribution


class ContributionAmendment(models.Model):
    """
    A proposal to change one or more sensitive fields on a Contribution.
    Goes through the contribution's own voting_threshold before being applied.

    Sensitive fields: fixed_amount, target_amount, voting_threshold,
                      end_date, period_months, visibility.
    """
    STATUS_CHOICES = (
        ('PENDING',   'Pending'),
        ('APPROVED',  'Approved'),
        ('REJECTED',  'Rejected'),
        ('WITHDRAWN', 'Withdrawn'),
    )

    contribution = models.ForeignKey(
        Contribution, on_delete=models.CASCADE, related_name='amendments'
    )
    proposed_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='proposed_amendments'
    )
    # JSON snapshot of proposed changes e.g. {"fixed_amount": "1500.00", "voting_threshold": "50"}
    changes      = models.JSONField()
    reason       = models.TextField(blank=True)
    status       = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    created_at   = models.DateTimeField(auto_now_add=True)
    resolved_at  = models.DateTimeField(null=True, blank=True)

    @property
    def approve_count(self):
        return self.votes.filter(vote='APPROVE').count()

    @property
    def reject_count(self):
        return self.votes.filter(vote='REJECT').count()

    def __str__(self):
        return f"Amendment #{self.id} on '{self.contribution.title}' [{self.status}]"



class ContributionAmendmentVote(models.Model):
    VOTE_CHOICES = (('APPROVE', 'Approve'), ('REJECT', 'Reject'))
    amendment = models.ForeignKey(ContributionAmendment, on_delete=models.CASCADE, related_name='votes')
    voter     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='amendment_votes')
    vote      = models.CharField(max_length=10, choices=VOTE_CHOICES)
    voted_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['amendment', 'voter']
