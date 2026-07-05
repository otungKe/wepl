"""
Provider registry — selects the active IdentityVerificationProvider.

Selection (settings.IDENTITY_PROVIDER):
    'manual' → ManualProvider (human review — production default)
    'fake'   → FakeProvider (tests / local dev, no network, auto-verifies)
    ''       → auto: 'fake' under DEBUG, else 'manual'

The '' → DEBUG default preserves WEPL's historical behaviour exactly: dev
auto-approves, production waits for a human reviewer. Tests can override the
active provider with ``use_provider()`` so the KYC path never hits the network.
"""
from __future__ import annotations

from functools import lru_cache

from django.conf import settings

from . import IdentityVerificationProvider

_override: IdentityVerificationProvider | None = None


@lru_cache(maxsize=None)
def _build(name: str) -> IdentityVerificationProvider:
    if name == 'manual':
        from .manual import ManualProvider
        return ManualProvider()
    if name == 'fake':
        from .fake import FakeProvider
        return FakeProvider()
    raise ValueError(f"Unknown IDENTITY_PROVIDER: {name!r}")


def get_provider() -> IdentityVerificationProvider:
    """Return the active provider (test override wins)."""
    if _override is not None:
        return _override
    name = (getattr(settings, 'IDENTITY_PROVIDER', '') or '').strip()
    if not name:
        name = 'fake' if settings.DEBUG else 'manual'
    return _build(name)


def use_provider(provider: IdentityVerificationProvider | None) -> None:
    """Install a provider override (tests/sandbox). Pass None to clear."""
    global _override
    _override = provider
