"""The domain half of the ledger's fund → tenant hook (Phase 6, P6-03).

The ledger stamps each sub-ledger account with the tenant that owns the pool,
but only the domain knows what a pool is. ``register()`` hands the ledger this
lookup at startup; see ``apps.ledger.fund_tenant`` for the other half.
"""
from apps.ledger.fund_tenant import register_fund_tenant_resolver

from .models import Contribution, SharesFund, WelfareFund

_MODELS = {
    'contribution': Contribution,
    'welfare':      WelfareFund,
    'shares':       SharesFund,
}


def tenant_for_fund(fund_type: str, fund_id: int):
    """The tenant of the community owning *fund_id*, or None."""
    model = _MODELS.get(fund_type)
    if model is None:
        return None
    obj = model.objects.filter(pk=fund_id).first()
    return getattr(getattr(obj, 'community', None), 'tenant', None)


def register() -> None:
    register_fund_tenant_resolver(tenant_for_fund)
