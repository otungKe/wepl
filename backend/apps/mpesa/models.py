from django.conf import settings
from django.db import models


class MpesaSTKRequest(models.Model):
    """Tracks an outbound STK Push request sent to a member's phone."""

    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('SUCCESS', 'Success'),
        ('FAILED', 'Failed'),
    )
    PAYMENT_TYPE_CHOICES = (
        ('contribution',     'Contribution'),
        ('welfare',          'Welfare Fund'),
        ('shares',           'Shares Fund'),
        ('advance_repayment','Advance Repayment'),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='stk_requests'
    )
    payment_type = models.CharField(
        max_length=20, choices=PAYMENT_TYPE_CHOICES, default='contribution'
    )
    contribution = models.ForeignKey(
        'contributions.Contribution', on_delete=models.CASCADE,
        related_name='stk_requests', null=True, blank=True,
    )
    welfare_fund = models.ForeignKey(
        'contributions.WelfareFund', on_delete=models.SET_NULL,
        related_name='stk_requests', null=True, blank=True,
    )
    shares_fund = models.ForeignKey(
        'contributions.SharesFund', on_delete=models.SET_NULL,
        related_name='stk_requests', null=True, blank=True,
    )
    advance = models.ForeignKey(
        'contributions.EmergencyAdvance', on_delete=models.SET_NULL,
        related_name='stk_requests', null=True, blank=True,
    )
    phone_number = models.CharField(max_length=20)
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    checkout_request_id = models.CharField(max_length=255, unique=True)
    merchant_request_id = models.CharField(max_length=255)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    result_code = models.IntegerField(null=True, blank=True)
    result_desc = models.TextField(null=True, blank=True)
    mpesa_receipt = models.CharField(max_length=50, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.phone_number} | KES {self.amount} | {self.status}"


class MpesaC2BTransaction(models.Model):
    """Records an inbound C2B payment from a member's M-Pesa to the group Paybill."""

    contribution = models.ForeignKey(
        'contributions.Contribution', on_delete=models.CASCADE,
        related_name='mpesa_transactions', null=True, blank=True
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='mpesa_transactions', null=True, blank=True
    )

    phone_number = models.CharField(max_length=20)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    mpesa_receipt = models.CharField(max_length=50, unique=True)
    transaction_date = models.DateTimeField()
    # account reference sent by the member (e.g. "WEPL-42" to match contribution 42)
    bill_ref_number = models.CharField(max_length=255)
    is_reconciled = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.phone_number} | KES {self.amount} | {self.mpesa_receipt}"
