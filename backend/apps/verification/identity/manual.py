"""
ManualProvider — the default, no-vendor identity checker.

It performs no automated verification: every submission is routed to a human
reviewer (Django admin → Approve/Reject KYC actions). This is exactly WEPL's
current production behaviour, now expressed through the provider port so a real
vendor can replace it without touching the KYC view.
"""
from __future__ import annotations

from . import IdentityCheckResult, IdentitySubject, IdentityVerificationProvider, MANUAL_REVIEW


class ManualProvider(IdentityVerificationProvider):
    name = 'manual'

    def verify_identity(self, subject: IdentitySubject) -> IdentityCheckResult:
        return IdentityCheckResult(
            state=MANUAL_REVIEW,
            provider=self.name,
            reason='Queued for manual review.',
        )
