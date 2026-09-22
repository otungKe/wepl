"""The seam between the M-Pesa rail and the business that gives a payment meaning.

``apps.mpesa`` owns the two rail records — an outbound STK request and an inbound
paybill deposit — and nothing else. When one of them settles, *what that means*
(credit a contribution, a welfare fund, a shares purchase, an advance repayment)
is the domain's business, and the domain sits above the rail.

So the rail app declares the moment here and ``apps.contributions`` registers the
handler from ``ContributionsConfig.ready()`` (ADR-0033). Handlers run
**synchronously, in the caller's transaction**, exactly where the direct call used
to run: an exception propagates untouched, so the STK task still retries and the
C2B reconciler still reports a failure to the caller.

There is deliberately at most one handler for each — these are routing decisions
with a single right answer, not notifications to fan out. Registering a second
one replaces the first.
"""
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_collection_settled: Optional[Callable[..., None]] = None
_paybill_resolver: Optional[Callable[..., dict]] = None


def register_collection_settled(fn: Callable[..., None]) -> None:
    """Register the handler for a settled pay-in. Called from an AppConfig.ready()."""
    global _collection_settled
    _collection_settled = fn


def register_paybill_resolver(fn: Callable[..., dict]) -> None:
    """Register the resolver for an inbound paybill deposit. Called from ready()."""
    global _paybill_resolver
    _paybill_resolver = fn


def run_collection_settled(**kwargs) -> None:
    """Route a settled collection to the domain.

    No handler registered means the domain app is not installed, which is a
    deployment mistake rather than a state to paper over: say so loudly and let
    the caller (a retrying Celery task) treat it as a failure.
    """
    if _collection_settled is None:
        raise RuntimeError(
            "No collection-settled handler registered — a settled M-Pesa payment "
            "has nowhere to go. apps.contributions must register one in ready()."
        )
    _collection_settled(**kwargs)


def resolve_paybill_payin(**kwargs) -> dict:
    """Ask the domain to resolve and credit an inbound paybill deposit.

    Returns the domain's result dict, which the rail layer stamps onto its own
    record: ``{reconciled, reason, contribution_id, user_id}``. With no resolver
    registered the deposit is recorded but left unreconciled for review — the
    money is already banked, so losing the row would be worse than a no-op.
    """
    if _paybill_resolver is None:
        logger.error(
            "No paybill resolver registered — C2B deposit recorded but not reconciled."
        )
        return {"reconciled": False, "reason": "no_resolver",
                "contribution_id": None, "user_id": None}
    return _paybill_resolver(**kwargs)
