"""Fund → tenant resolution, inverted so the ledger does not import the domain.

A sub-ledger account is stamped with the tenant that owns the pool it belongs
to (Phase 6, P6-03). Working that out means looking at a ``Contribution``,
``WelfareFund`` or ``SharesFund`` — domain models the ledger must not know
about, because the ledger sits underneath them.

So the ledger declares the hook and the domain fills it in:
``apps.contributions.apps.ContributionsConfig.ready()`` calls
:func:`register_fund_tenant_resolver`, the same way it registers its settlement
targets. With no resolver registered the ledger still works and every account is
stamped ``None`` (shared), which is what the pre-registration code did on any
failure and is safe under RLS — a null tenant is visible.
"""
from typing import Callable, Optional

# fn(fund_type: str, fund_id: int) -> tenant instance | None
_resolver: Optional[Callable[[str, int], object]] = None


def register_fund_tenant_resolver(fn: Callable[[str, int], object]) -> None:
    """Install the domain's fund → tenant lookup. Called once, from ready()."""
    global _resolver
    _resolver = fn


def resolve_fund_tenant(fund_type: str, fund_id: int):
    """The tenant owning *fund_id*, or None if unknown or unresolvable.

    Never raises: account creation must not fail because a pool's community or
    tenant could not be read. None means "shared", which RLS treats as visible.
    """
    if _resolver is None:
        return None
    try:
        return _resolver(fund_type, fund_id)
    except Exception:
        return None
