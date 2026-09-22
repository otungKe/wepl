"""The pre-posting chokepoint (ADR-0007), inverted so the ledger stays a leaf.

Every member-facing money movement passes through exactly one enforcement point
before a journal is written. That enforcement is *policy* — limits, risk, account
restrictions — and policy belongs above the book of record, not inside it. So the
ledger owns the chokepoint and the controls app fills it: ``ControlsConfig.ready()``
calls :func:`register_pre_posting_check`, and ``post_journal`` runs whatever is
registered.

Checks are expected to raise (``LimitExceeded`` on DENY, ``ControlHeld`` on HOLD).
Those exceptions are the mechanism, so they propagate untouched — a check that
fails is a posting that must not happen. With nothing registered the ledger posts
unguarded, which is the correct behaviour for a deployment that has no controls
app installed, and is what the tests that exercise the ledger core alone rely on.
"""
from typing import Callable, List

# fn(*, financial_transaction, amount) -> None; raises to block the posting.
_checks: List[Callable[..., None]] = []


def register_pre_posting_check(fn: Callable[..., None]) -> None:
    """Install a check that runs before every member-facing journal is written."""
    if fn not in _checks:
        _checks.append(fn)


def run_pre_posting_checks(*, financial_transaction, amount) -> None:
    """Run every registered check. Any exception raised here blocks the posting."""
    for check in _checks:
        check(financial_transaction=financial_transaction, amount=amount)
