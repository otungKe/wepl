"""
Provider registry — selects the active PaymentProvider.

Selection (settings.PAYMENT_PROVIDER):
    'mpesa' → MpesaProvider (live / Daraja sandbox)
    'fake'  → FakeProvider (tests / local sandbox, no network)
    ''      → auto: 'fake' under DEBUG, else 'mpesa'

Tests can override the active provider with ``use_provider()`` so money-path code
never hits the network.
"""
from __future__ import annotations

from functools import lru_cache

from django.conf import settings

from . import PaymentProvider

_override: PaymentProvider | None = None


@lru_cache(maxsize=None)
def _build(name: str) -> PaymentProvider:
    if name == 'mpesa':
        from .mpesa import MpesaProvider
        return MpesaProvider()
    if name == 'fake':
        from .fake import FakeProvider
        return FakeProvider()
    raise ValueError(f"Unknown PAYMENT_PROVIDER: {name!r}")


def get_provider() -> PaymentProvider:
    """Return the active provider (test override wins)."""
    if _override is not None:
        return _override
    name = (getattr(settings, 'PAYMENT_PROVIDER', '') or '').strip()
    if not name:
        name = 'fake' if settings.DEBUG else 'mpesa'
    return _build(name)


def use_provider(provider: PaymentProvider | None) -> None:
    """Install a provider override (tests/sandbox). Pass None to clear."""
    global _override
    _override = provider
