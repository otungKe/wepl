"""Phone-number normalisation.

Kenyan MSISDNs reach the API in many shapes depending on the client and how a
user typed them: ``0712345678``, ``712345678``, ``+254712345678`` or
``254712345678``. Historically the auth views stored and looked up the phone
*exactly* as received, so an account created from one shape could not be found
when a different client sent another shape — e.g. a number registered on mobile
as ``0712…`` could not log in from the web, which normalises to ``254712…``.

``normalize_phone`` collapses all of these to the canonical ``2547XXXXXXXX`` /
``2541XXXXXXXX`` form so storage and lookup are always consistent. Inputs that
don't look Kenyan are returned digits-only and left for downstream validation
to reject.
"""
import re


def normalize_phone(raw: str | None) -> str:
    if not raw:
        return ""
    digits = re.sub(r"\D", "", raw)  # drop '+', spaces, dashes, etc.
    if digits.startswith("0"):
        return "254" + digits[1:]
    if digits.startswith("7") or digits.startswith("1"):
        return "254" + digits
    return digits


def mask_phone(raw: str | None) -> str:
    """Partially mask an MSISDN for client-facing display, keeping enough to
    recognise it: a leading prefix and the last 3 digits, the middle hidden —
    e.g. ``254712345678`` → ``254712***678``.

    This is the *client* view; operators (ops console) always see the full
    number. Short/non-numeric inputs are masked wholesale rather than leaked.
    """
    if not raw:
        return ""
    digits = re.sub(r"\D", "", raw)
    # Too short to reveal any part safely — hide it all.
    if len(digits) < 7:
        return "*" * len(digits) if digits else ""
    prefix = digits[:6]   # e.g. "254712" — country + operator, not identifying
    last = digits[-3:]
    return f"{prefix}{'*' * (len(digits) - 9)}{last}" if len(digits) > 9 else f"{prefix}***{last}"
