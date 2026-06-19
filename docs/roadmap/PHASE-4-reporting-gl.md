# Phase 4 — Reporting & General Ledger

**Status:** 🔴 Not started · **Depends on:** Phase 0

## Objective
Turn the now-authoritative double-entry ledger into financial reporting: trial
balance, balance sheet and income statement per community/fund, statements of
account, and auditor-grade exports. Trivial once Phase 0 is done; impossible before.

## Work items
- **P4-01** Trial balance report (global + per dimension: community, fund, op_type).
- **P4-02** Balance sheet & income statement from GL classifications (ASSET/
  LIABILITY/EQUITY/INCOME/EXPENSE already modelled on `Account`).
- **P4-03** Member/group statement of account (period activity + running balance)
  from `JournalLine`.
- **P4-04** Immutable audit export (CSV/JSON, WORM-friendly) of journals + lines.
- **P4-05** Read-model/materialised views for heavy reports; keep raw lines as truth.
- **P4-06** Scheduled close/period snapshots.

## Acceptance criteria
- Reports reconcile to the ledger to the cent; global trial balance is zero.
- Statements are reproducible from immutable lines at any past point in time.

## Exit criteria
- [ ] Self-serve financial statements per community/fund.
- [ ] Auditable export pipeline.
