# ADR-0001: Ledger-first, double-entry as the single book of record

- **Status:** Accepted
- **Date:** 2026-06-19
- **Deciders:** Architecture review

## Context
WEPL tracks money in three places: mutable balance columns (the de-facto truth used
by business logic), a legacy single-entry `LedgerEntry` shadow, and a correct but
dormant double-entry core (`Account`/`JournalEntry`/`JournalLine`/`AccountBalance`).
Drift between them is a recurring certainty (a nightly job exists only to detect it).
A single-entry ledger cannot produce a trial balance, balance sheet, or prove
conservation of money. Enterprise cores (Finacle, Temenos, Thought Machine, Mambu)
are ledger-first: the ledger *is* the system and everything derives from it.

## Decision
The double-entry core becomes the **single source of monetary truth**. All balances
are derived from immutable `JournalLine`s (via the `AccountBalance` projection,
rebuildable by replay). Any surviving balance column is a cache, never truth.

## Consequences
- **+** Provable correctness (global trial balance = 0), real GL, real reporting.
- **+** One place to add limits, risk, audit, multi-currency, settlement.
- **−** Requires a cutover (Phase 0) and deletion of working legacy code.
- **−** Balance reads move from O(1) column lookups to projection reads (already
  designed and indexed in `AccountBalance`).

## Alternatives considered
- *Keep dual/triple-write + reconcile forever:* rejected — permanent drift risk and
  no path to GL/reporting.
- *Promote the single-entry ledger:* rejected — single-entry can't express the
  accounting equation.
