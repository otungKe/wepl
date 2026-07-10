"""
Identifier helpers.

``uuid7()`` — a time-ordered UUID (RFC 9562 version 7). Opaque and safe to
expose externally, yet monotonic enough for index locality. Used for
``account_uid`` (ADR-0025) as an external/BaaS handle distinct from the internal
bigint PK. Hand-rolled because the stdlib gains ``uuid.uuid7`` only in Python
3.14; drop-in replaceable when we're there.
"""
from __future__ import annotations

import os
import time
from uuid import UUID


def uuid7() -> UUID:
    """A version-7 (time-ordered) UUID.

    Layout (128 bits): 48-bit Unix ms timestamp | 4-bit version (0b0111) |
    12 random bits | 2-bit variant (0b10) | 62 random bits.
    """
    unix_ms = int(time.time() * 1000) & ((1 << 48) - 1)
    rand = int.from_bytes(os.urandom(10), "big")   # 80 random bits
    rand_a = (rand >> 68) & 0xFFF                   # 12 bits
    rand_b = rand & ((1 << 62) - 1)                 # 62 bits

    value = unix_ms << 80
    value |= 0x7 << 76           # version 7
    value |= rand_a << 64
    value |= 0b10 << 62          # variant (RFC 4122/9562)
    value |= rand_b
    return UUID(int=value)
