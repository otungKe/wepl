"""
Field-level encryption at rest (Fernet / AES-128-CBC + HMAC).

Used for secrets that must be *recoverable* (not merely comparable) — e.g. an
operator's TOTP seed, which the server has to decrypt to compute the expected
code. Values that only need equality checks (passwords, recovery codes) stay
one-way hashed and never come through here.

Keys come from ``settings.FIELD_ENCRYPTION_KEYS`` (a list of urlsafe-base64
Fernet keys). The first key encrypts; every key can decrypt, so rotation is
"prepend the new key, re-save, drop the old one later". When unset, a key is
derived deterministically from ``SECRET_KEY`` so dev/test work with no extra
config — production sets explicit keys (rotating SECRET_KEY must not silently
strand ciphertext).
"""
from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.db import models


def _derive_key(secret: str) -> bytes:
    """A stable Fernet key (32 urlsafe-base64 bytes) derived from a secret."""
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())


@lru_cache(maxsize=1)
def _cipher() -> MultiFernet:
    keys = list(getattr(settings, "FIELD_ENCRYPTION_KEYS", []) or [])
    if not keys:
        keys = [_derive_key(settings.SECRET_KEY).decode()]
    return MultiFernet([Fernet(k.encode() if isinstance(k, str) else k) for k in keys])


def encrypt(plaintext: str) -> str:
    return _cipher().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    """Decrypt a token. If it isn't a valid Fernet token (e.g. legacy plaintext
    written before this field was encrypted), return it unchanged so a value is
    never lost — the next save re-writes it encrypted."""
    try:
        return _cipher().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return token


class EncryptedTextField(models.TextField):
    """A TextField whose value is transparently encrypted at rest and decrypted
    on load. Stored ciphertext is opaque, so the column is not usefully
    queryable — reserve this for recoverable secrets, not lookup keys."""

    def from_db_value(self, value, expression, connection):
        if value in (None, ""):
            return value
        return decrypt(value)

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value in (None, ""):
            return value
        return encrypt(value)
