"""Signed, time-limited download tokens (ADR-0018).

A download URL carries a signed token (the capability): no DB session needed, so
<img src> works, while access is unguessable and expires. The token binds the
file id; tampering or expiry is rejected by the signer.
"""
from django.core import signing

_signer = signing.TimestampSigner(salt='files.download')
DEFAULT_TTL = 600  # seconds


def make_token(file_id) -> str:
    return _signer.sign(str(file_id))


def read_token(token: str, *, max_age: int = DEFAULT_TTL) -> str | None:
    """Return the file id if the token is valid and unexpired, else None."""
    try:
        return _signer.unsign(token, max_age=max_age)
    except signing.BadSignature:
        return None
