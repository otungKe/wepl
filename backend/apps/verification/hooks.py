"""Reactions other apps attach to a case decision, inverted so verification
does not import them (ADR-0033).

Deciding a case has consequences outside the case ledger — releasing the held
movement an EDD case was opened over, issuing the pre-clearance that lets the
customer's retry through, resolving the customer-facing request row, telling a
KYC applicant the outcome. Those rows and those messages belong to
``apps.controls`` and ``apps.users``, both of which already import this app.
Rather than reach back into their tables and their private helpers from here,
verification declares the moments and they register what to do with them from
their own ``AppConfig.ready()``.

The two slots differ, deliberately, in where they run:

``subject_case_decided`` runs **inside the deciding transaction**, in
registration order, at the exact point the inline code used to run. Handlers are
part of the decision, not a notification about it: an exception propagates and
rolls the decision back.

``kyc_decided`` runs **after that transaction has committed**, which is where
``decide()``'s inline ``_notify`` call sat. A handler cannot roll the decision
back — it is already durable — and a raising one surfaces to the caller exactly
as the inline call did.
"""
from typing import Callable, List

# fn(*, case, action, actor_label, reason) -> None
_subject_case_decided: List[Callable[..., None]] = []


def register_subject_case_decided(fn: Callable[..., None]) -> None:
    """Attach a reaction to ``decide_subject_case``. Called once, from ready()."""
    if fn not in _subject_case_decided:
        _subject_case_decided.append(fn)


def run_subject_case_decided(*, case, action: str, actor_label: str, reason: str) -> None:
    """Run every registered reaction. Raising here rolls the decision back."""
    for handler in _subject_case_decided:
        handler(case=case, action=action, actor_label=actor_label, reason=reason)


# fn(*, kyc, action) -> None
_kyc_decided: List[Callable[..., None]] = []


def register_kyc_decided(fn: Callable[..., None]) -> None:
    """Attach a reaction to a decided KYC case. Called once, from ready()."""
    if fn not in _kyc_decided:
        _kyc_decided.append(fn)


def run_kyc_decided(*, kyc, action: str) -> None:
    """Run every registered reaction, after the decision has committed.

    Nothing is registered in a test that does not load ``apps.users``; the
    decision still stands, it is simply not announced.
    """
    for handler in _kyc_decided:
        handler(kyc=kyc, action=action)
