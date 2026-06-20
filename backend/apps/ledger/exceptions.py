"""
Ledger-domain exceptions.

Kept separate from apps.core.exceptions because these are accounting-engine
invariants, not HTTP concerns. The double-entry writer raises these; callers
that want HTTP status mapping can catch and translate at the view layer.
"""


class LedgerError(Exception):
    """Base class for all double-entry ledger errors."""


class UnbalancedJournalError(LedgerError):
    """
    Raised by post_journal() when the supplied lines do not satisfy the
    fundamental double-entry invariant:

        Σ(debit amounts) == Σ(credit amounts),  with at least two lines.

    This is the application-layer guard. The database additionally enforces
    the same invariant at COMMIT via a deferred constraint trigger, so even a
    raw-SQL writer cannot persist an unbalanced journal.
    """


class JournalImmutableError(LedgerError):
    """Raised on any attempt to mutate or delete a posted JournalEntry/JournalLine."""
