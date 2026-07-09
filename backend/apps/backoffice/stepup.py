"""
Step-up (re-authentication) for the Back Office — TOTP + short-lived elevation.

An operator's 12-hour shift JWT (``auth.py``) proves *who* they are for the
shift. It is deliberately not enough to fire a destructive lever. Step-up adds a
second, short-lived proof — a fresh TOTP code — that grants a ~5-minute elevated
window, carried on the flagged request as an ``X-Ops-StepUp`` token and enforced
by ``RequireStepUp`` (``permissions.py``).

TOTP is time-based (RFC 6238): a secret shared once at enrolment plus the current
30-second window derive the same six digits independently on both ends, so
verification needs no network round-trip and adds no SMS dependency to the money
path. See the Production Operations Roadmap (OP-3).

Hardening follow-up: ``totp_secret`` is stored as issued. It sits in the same
trust boundary as the operator password hash; encrypting it at rest (a
field-level KMS/Fernet layer) is a deliberate later step, noted on the model.
"""
from __future__ import annotations

import secrets
from datetime import timedelta

import jwt
import pyotp
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.utils import timezone

STEPUP_TOKEN_TYPE = "ops-stepup"
STEPUP_TTL = timedelta(minutes=5)
STEPUP_HEADER = "HTTP_X_OPS_STEPUP"          # request.META key for X-Ops-StepUp
ISSUER = "WEPL Operations"
RECOVERY_CODE_COUNT = 10


# ── TOTP primitives ──────────────────────────────────────────────────────────
def generate_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, label: str) -> str:
    """The ``otpauth://`` URI an authenticator app scans (rendered as a QR by the
    console). It embeds the secret — return it only to the enrolling operator."""
    return pyotp.TOTP(secret).provisioning_uri(name=label, issuer_name=ISSUER)


def verify_code(secret: str, code: str) -> bool:
    if not secret or not code:
        return False
    # valid_window=1 tolerates a ±30s clock skew between the app and the server.
    return pyotp.TOTP(secret).verify(str(code).strip(), valid_window=1)


# ── Recovery codes (single-use, hashed at rest like passwords) ───────────────
def generate_recovery_codes(n: int = RECOVERY_CODE_COUNT) -> tuple[list[str], list[str]]:
    """Return ``(plaintext, hashed)``. Plaintext is shown once to the operator;
    only the hashes are persisted."""
    plain = ["-".join(secrets.token_hex(2) for _ in range(3)) for _ in range(n)]
    hashed = [make_password(c) for c in plain]
    return plain, hashed


def consume_recovery_code(hashed_codes: list[str], code: str) -> list[str] | None:
    """Return the remaining hashes with the matched code removed, or ``None`` if
    no code matched. Single-use — a consumed code cannot be replayed."""
    code = (code or "").strip()
    if not code:
        return None
    for i, h in enumerate(hashed_codes or []):
        if check_password(code, h):
            return [*hashed_codes[:i], *hashed_codes[i + 1:]]
    return None


# ── Step-up elevation token (stateless, 5-minute) ────────────────────────────
def issue_stepup_token(staff) -> str:
    """Mint a short-lived elevation token. Only ever called after a TOTP/recovery
    code has actually been verified — the token itself is the proof-of-proof."""
    now = timezone.now()
    payload = {
        "type": STEPUP_TOKEN_TYPE,
        "sid": staff.id,
        "iat": int(now.timestamp()),
        "exp": int((now + STEPUP_TTL).timestamp()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def stepup_token_valid(token: str, staff) -> bool:
    if not token:
        return False
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        return False
    return payload.get("type") == STEPUP_TOKEN_TYPE and payload.get("sid") == staff.id
