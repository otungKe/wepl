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
