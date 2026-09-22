"""Scheduled recurring payouts from a pool."""

from django.conf import settings
from django.db import models

from .contribution import Contribution


class StandingOrder(models.Model):
    FREQUENCY_CHOICES = (
        ('daily',   'Daily'),
        ('weekly',  'Weekly'),
        ('monthly', 'Monthly'),
    )
    PAYEE_TYPE_CHOICES = (
        ('fixed',    'Fixed Payee'),
        ('rotating', 'Rotating Payees'),
    )

    contribution      = models.ForeignKey(Contribution, on_delete=models.CASCADE, related_name='standing_orders')
    created_by        = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    amount            = models.DecimalField(max_digits=12, decimal_places=2)
    frequency         = models.CharField(max_length=10, choices=FREQUENCY_CHOICES)
    payee_type        = models.CharField(max_length=10, choices=PAYEE_TYPE_CHOICES, default='fixed')
    fixed_payee_phone = models.CharField(max_length=20, blank=True, null=True)
    is_active         = models.BooleanField(default=True)
    created_at        = models.DateTimeField(auto_now_add=True)
    # Schedule tracking — prevents the Celery task from firing every run
    next_run_at      = models.DateTimeField(null=True, blank=True, db_index=True)
    last_executed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.contribution.title} | KES {self.amount} | {self.frequency} | {self.payee_type}"



class StandingOrderSlot(models.Model):
    order        = models.ForeignKey(StandingOrder, on_delete=models.CASCADE, related_name='slots')
    phone_number = models.CharField(max_length=20)
    name         = models.CharField(max_length=120, blank=True, default='')
    slot_order   = models.PositiveIntegerField()
    has_received = models.BooleanField(default=False)
    received_at  = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['slot_order']
        unique_together = ['order', 'slot_order']

    def __str__(self):
        return f"Slot {self.slot_order} — {self.phone_number}"


# ---------------------------------------------------------------------------
# Multi-signature Disbursement Requests
# ---------------------------------------------------------------------------
