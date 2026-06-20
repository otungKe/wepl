# ADR-0004: `post_journal()` is the single money-mutation entrypoint

- **Status:** Accepted
- **Date:** 2026-06-19
- **Phase:** 0 (P0-05), enforced ongoing

## Context
Money is currently mutated in many places: `F()` updates on balance columns across
`apps/contributions/services.py`, `write_ledger_entry` in `apps/ledger/writer.py`,
direct `WelfareFund.balance` updates in `apps/ledger/tasks.py`, and `total_pool`
updates in `apps/mpesa/views.py`. Cross-cutting controls (limits, risk, audit) have
no single place to live.

## Decision
After Phase 0, **all** value movement goes through `post_journal()` (and
`reverse_journal()` for corrections). `FinancialTransaction` remains the
orchestration/state-machine layer and links to the resulting `JournalEntry`. Direct
writes to balances or ledger rows from anywhere else are prohibited.

## Enforcement
- Code review rule + a CI grep guard failing on new direct balance/ledger writes
  outside `apps/ledger/posting.py`.
- The DB-level deferred balance trigger (migration `0003`) remains the last line of
  defence (`Σdebit == Σcredit`).

## Consequences
- **+** One chokepoint for limits/risk/audit/multi-currency (Phases 3, 5, 8).
- **+** Idempotency and balance invariants enforced uniformly.
- **−** Slightly more ceremony for simple movements; justified by the guarantees.

## Alternatives considered
- *Multiple sanctioned writers per domain:* rejected — recreates the dispersal of
  money logic this ADR removes.
