"""
Manual payment recording has been removed.

ALL contribution payments now flow exclusively through M-Pesa STK Push:
  POST /api/mpesa/stk-push/  →  Daraja STK Push  →  STKCallbackView
    → ContributionService.contribute()  →  LedgerEntry + ContributionTransaction

There is exactly ONE canonical path for recording a contribution payment.
Any attempt to add a second path here will be rejected in code review.
"""
