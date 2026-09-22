"""Governance actions on a pool that need approval before they run."""

from django.conf import settings
from django.db import models

from .contribution import Contribution


class PoolActionRequest(models.Model):
    """A governed collective-fund action awaiting a second admin's approval
    (ADR-0027 maker-checker). Spending pool funds or declaring a distribution
    moves *members'* money, so it never executes on one admin's say-so — a second
    admin must approve first. External income (money in) is benign and stays
    direct. On approval the request executes through the ledger and records the
    resulting FinancialTransaction.
    """
    class Action(models.TextChoices):
        EXPENSE      = 'EXPENSE',      'Pool expense'
        DISTRIBUTION = 'DISTRIBUTION', 'Surplus distribution'

    class Status(models.TextChoices):
        PENDING   = 'PENDING',   'Pending approval'
        EXECUTED  = 'EXECUTED',  'Executed'
        REJECTED  = 'REJECTED',  'Rejected'
        CANCELLED = 'CANCELLED', 'Cancelled'

    contribution = models.ForeignKey(
        Contribution, on_delete=models.CASCADE, related_name='pool_actions')
    action       = models.CharField(max_length=20, choices=Action.choices)
    amount       = models.DecimalField(max_digits=20, decimal_places=2)
    apportion    = models.CharField(max_length=12, default='pro_rata')
    memo         = models.CharField(max_length=255, blank=True)
    status       = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    decided_by   = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    decision_note = models.CharField(max_length=255, blank=True)
    # The ledger movement produced on execution (the book of record).
    financial_transaction = models.ForeignKey(
        'ledger.FinancialTransaction', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+')
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['contribution', 'status'], name='pool_action_contrib_status_idx'),
        ]

    def __str__(self):
        return f"{self.action} {self.amount} [{self.status}] — {self.contribution.title}"



class PoolActionApproval(models.Model):
    """A distinct admin's approval of a PoolActionRequest (maker-checker)."""
    request   = models.ForeignKey(
        PoolActionRequest, on_delete=models.CASCADE, related_name='approvals')
    approver  = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['request', 'approver']
