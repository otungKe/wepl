"""
FakeProvider — deterministic identity checker for tests and local development.

No network. By default it VERIFIES every submission (so developers get full app
access instantly, matching the old DEBUG auto-approve behaviour). Tests can flip
it to REJECTED or MANUAL_REVIEW to exercise those branches.
"""
from __future__ import annotations

from . import (
    IdentityCheckResult,
    IdentitySubject,
    IdentityVerificationProvider,
    MANUAL_REVIEW,
    REJECTED,
    VERIFIED,
)


class FakeProvider(IdentityVerificationProvider):
    name = 'fake'

    def __init__(self, *, outcome: str = VERIFIED, reason: str = ''):
        self.outcome = outcome
        self.reason  = reason

    def verify_identity(self, subject: IdentitySubject) -> IdentityCheckResult:
        reason = self.reason or {
            VERIFIED:      'Identity verified (fake provider).',
            REJECTED:      'Identity rejected (fake provider).',
            MANUAL_REVIEW: 'Queued for manual review (fake provider).',
        }.get(self.outcome, '')
        return IdentityCheckResult(
            state=self.outcome,
            provider=self.name,
            provider_ref='fake-ref',
            reason=reason,
            raw={'subject_id_number': subject.id_number},
        )
