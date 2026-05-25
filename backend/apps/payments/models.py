from django.conf import settings
from django.db import models

from apps.contributions.models import Contribution


class Payment(models.Model):

    # -----------------------------
    # PAYMENT STATUS TRACKING
    # Important for M-Pesa + future gateways
    # -----------------------------
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),     # initiated but not confirmed
        ('COMPLETED', 'Completed'), # successful payment
        ('FAILED', 'Failed'),       # failed transaction
        ('REVERSED', 'Reversed'),   # refunded/reversed
    )

    # -----------------------------
    # LINK TO CONTRIBUTION (SACCO POOL)
    # -----------------------------
    contribution = models.ForeignKey(
        Contribution,
        on_delete=models.CASCADE,
        related_name='payments'
    )

    # -----------------------------
    # USER WHO MADE THE PAYMENT
    # (ALWAYS phone_number-based system)
    # -----------------------------
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='payments'
    )

    # -----------------------------
    # PAYMENT AMOUNT
    # -----------------------------
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    # -----------------------------
    # EXTERNAL REFERENCE (M-PESA / CASH REF)
    # -----------------------------
    reference = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    # -----------------------------
    # PAYMENT STATUS
    # -----------------------------
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='COMPLETED'
    )

    # -----------------------------
    # WHO RECORDED THE PAYMENT
    # (admin, system, or self-recorded)
    # -----------------------------
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='recorded_payments'
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['contribution', '-created_at'], name='payment_contrib_date_idx'),
            models.Index(fields=['user',         '-created_at'], name='payment_user_date_idx'),
        ]

    def __str__(self):
        # Mobile-friendly identity display
        return f"{self.user.phone_number} - {self.amount}"