"""The client address recorded on sessions and audit rows.

Takes the left-most X-Forwarded-For entry, falling back to REMOTE_ADDR, and
returns it only if it parses as an IP address. Those rows land in ``inet``
columns: an unparseable value (the header is caller-supplied) used to fail the
insert, which the audit writers swallowed, so a crafted header erased the
audit row, or broke the surrounding transaction.

The left-most entry is still whatever the caller claims. Reading it from the
right needs the number of proxies in front of the app confirmed on Render.
"""
import ipaddress


def _valid(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


def client_ip(request):
    if request is None:
        return None
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        ip = _valid(xff.split(",")[0])
        if ip:
            return ip
    return _valid(request.META.get("REMOTE_ADDR"))
