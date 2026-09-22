"""Per-request context established during authentication.

Some things must be set up once a request's principal is known and before the
view touches the database — today that is the RLS tenant GUC (ADR-0008), pinned
so Postgres restricts the connection to the caller's rows.

The app that *decides* that context (``apps.tenants``) and the app that *knows
when the principal is resolved* (``apps.users``) are peers: neither belongs below
the other, and having one import the other is what kept both inside the app
import cycle. So the registry lives here, in the foundation both already depend
on, and ``apps.core`` holds nothing but an opaque list of callables (ADR-0031,
ADR-0033).

Handlers are registered from an ``AppConfig.ready()``, receive ``user`` and
``request`` as keyword arguments, and run **synchronously inside
authentication**. Their exceptions propagate: a handler that cannot establish the
context it owns must fail the request rather than let it proceed unscoped.
Registration is idempotent.
"""
from typing import Callable, List

_post_authenticate: List[Callable[..., None]] = []


def register_post_authenticate(fn: Callable[..., None]) -> None:
    """Register a callable to run once a request's user has been resolved."""
    if fn not in _post_authenticate:
        _post_authenticate.append(fn)


def run_post_authenticate(*, user, request) -> None:
    """Run every registered handler. Called by the authenticator, nowhere else."""
    for hook in _post_authenticate:
        hook(user=user, request=request)
