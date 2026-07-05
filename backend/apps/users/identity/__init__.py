"""
IdentityVerificationProvider port — the vendor-agnostic contract for checking
that a KYC applicant is who they claim to be.

KYC review code speaks only this interface; concrete checkers (today: human
review; tomorrow: an automated identity-verification vendor or a direct
government-registry lookup) live behind adapters and never leak their wire
format upward. A FakeProvider implements the same contract so KYC-path tests
run with no network. This mirrors the PaymentProvider port (ADR-0005).

The port takes a normalised ``IdentitySubject`` (never the ORM row) and returns
a normalised ``IdentityCheckResult``. Each adapter translates to/from its own
vendor format.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


# ── Normalised outcome states (vendor-agnostic) ──────────────────────────────
# The KYC row's own status is derived from these:
#   VERIFIED       → status 'approved'
#   REJECTED       → status 'rejected'
#   MANUAL_REVIEW  → status 'pending'  (a human decides)
#   PENDING        → status 'pending'  (async vendor; outcome arrives via webhook)
VERIFIED      = 'verified'
REJECTED      = 'rejected'
MANUAL_REVIEW = 'manual_review'
PENDING       = 'pending'


@dataclass(frozen=True)
class IdentitySubject:
    """The claimed identity to check — assembled from a KYCProfile but decoupled
    from it so adapters never import models. Image fields are storage paths/keys,
    not open file handles; an adapter that needs the bytes opens them itself."""
    id_number:     str
    given_names:   str
    surname:       str
    date_of_birth: str                 # ISO-8601 date string
    id_front_path: str | None = None
    id_back_path:  str | None = None
    selfie_path:   str | None = None


@dataclass(frozen=True)
class IdentityCheckResult:
    """Outcome of an identity check. ``state`` is one of the constants above."""
    state:        str
    provider:     str                  # adapter name that produced this result
    provider_ref: str = ''             # vendor correlation id (for async/webhooks)
    reason:       str = ''             # human-readable outcome / why rejected
    raw:          dict = field(default_factory=dict)

    @property
    def is_terminal(self) -> bool:
        """True when no further vendor callback is expected."""
        return self.state in (VERIFIED, REJECTED, MANUAL_REVIEW)


class IdentityVerificationError(Exception):
    """Raised by adapters for unrecoverable vendor errors."""


class IdentityVerificationProvider(ABC):
    """An identity checker. Implementations must be stateless and side-effect-free
    except for the network calls they make."""

    name: str = 'base'

    @abstractmethod
    def verify_identity(self, subject: IdentitySubject) -> IdentityCheckResult:
        """Check the claimed identity and return a normalised result.

        A synchronous vendor returns VERIFIED/REJECTED directly. An asynchronous
        vendor returns PENDING with a ``provider_ref`` and delivers the final
        outcome later via ``parse_callback``."""

    def parse_callback(self, payload: dict) -> IdentityCheckResult:
        """Translate a raw inbound vendor webhook into an IdentityCheckResult.

        Optional — synchronous adapters (manual review, fake) never receive
        callbacks and may leave this unimplemented."""
        raise NotImplementedError(f"{self.name} does not support parse_callback()")
