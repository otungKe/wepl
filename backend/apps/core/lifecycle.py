"""The customer lifecycle seam: closing an account and exporting its data.

Every context holds some of a customer's data and some reasons an account may
not close yet. Rather than one view reaching into each context's tables (the
boundary audit's finding 16), each context registers what it knows from its own
``AppConfig.ready()``:

``blockers(user) -> list[str]``
    Customer-facing reasons the account cannot close yet. Empty = no objection.
``erase(user) -> None``
    Remove or anonymise this context's personal data about the user. Runs inside
    the closing transaction; a raise rolls the whole closure back. Work that
    cannot be undone (deleting a stored file) belongs in ``on_commit``.
``export(user) -> dict``
    This context's sections of the self-serve data export, keyed by section.

``apps.users.lifecycle`` runs them. A lost registration fails silently, so
``apps/users/tests_lifecycle.py`` asserts the expected set is registered.
"""
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass(frozen=True)
class Participant:
    name: str
    blockers: Optional[Callable] = None
    erase: Optional[Callable] = None
    export: Optional[Callable] = None


_participants: dict[str, Participant] = {}


def register(name: str, *, blockers=None, erase=None, export=None) -> None:
    """Register (or replace) one context's lifecycle hooks. Called from ready()."""
    _participants[name] = Participant(name, blockers, erase, export)


def participants() -> list[Participant]:
    return list(_participants.values())
