"""Reactions other apps attach to a case decision, inverted so verification
does not import them (ADR-0033).

Deciding an EDD case has consequences outside the case ledger — releasing the
held movement it was opened over, issuing the pre-clearance that lets the
customer's retry through. Those rows belong to ``apps.controls``, which already
imports this app to open the case in the first place. Rather than reach back
into controls' tables from here, verification declares the moment and controls
registers what to do with it from its own ``AppConfig.ready()``.

Handlers run **inside the deciding transaction**, in registration order, at the
exact point the inline code used to run. They are part of the decision, not a
notification about it: an exception propagates and rolls the decision back.
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
