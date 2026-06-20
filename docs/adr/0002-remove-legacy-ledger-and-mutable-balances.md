# ADR-0002: Remove the legacy single-entry ledger and mutable balance fields

- **Status:** Accepted
- **Date:** 2026-06-19
- **Deciders:** Project owner + architecture review
- **Implements:** [ADR-0001](0001-ledger-first-double-entry.md) · **Phase:** 0

## Context
The legacy single-entry ledger (`apps/ledger/writer.py`, `queries.py`, model
`LedgerEntry`) and the mutable balance fields (`Contribution.current_amount`,
`WelfareFund.balance`, `SharesFund.total_pool`, `ContributionAccount`,
`ContributionBalance`) plus dead compat fields (`contribution_type`, `cycle_amount`,
`min_approvals`, `deadline`) are the live implementation of every money path. They
are explicitly marked "LEGACY"/"backwards compatibility" in the code. No serious
testing and no production traffic have occurred.

## Decision
Delete all of the above and route every money path through the double-entry core.
Because there is no production data of value, we perform a **clean reset** rather
than backfilling historical journals: existing dev/test rows are discarded at
cutover. Deletion happens **only after** the new posting paths and ledger-derived
reads are merged and green (Phase 0 items P0-05/06 precede P0-07).

## Consequences
- **+** Eliminates the triple-source-of-truth and the drift class of bugs.
- **+** Forces the new core to be load-bearing and fully exercised.
- **−** A window where money-path code is being rewired; mitigated by additive-first
  sequencing and a green-test gate.
- **−** Irreversible-feeling at P0-07; mitigated by per-PR git revertability and the
  pre-production no-data posture.

## Reversal condition
If real balances exist at execution time, this ADR is **superseded** by a new ADR
switching P0-09 from "reset" to "backfill + parallel-run reconciliation."

## Alternatives considered
- *Deprecate-in-place and keep legacy as fallback:* rejected — perpetuates dual
  maintenance and drift; the user explicitly asked to wipe legacy.
