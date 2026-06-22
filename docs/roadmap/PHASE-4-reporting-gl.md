# Phase 4 — Reporting & General Ledger

**Status:** 🟢 Done (core) · **Depends on:** Phase 0

Implemented in `apps/ledger/reporting.py` (pure reads from immutable
`JournalLine`, point-in-time via `as_of`, dimension filters for
community/fund/op_type), a staff-gated read-only API under `/api/ledger/reports/`,
and the `export_ledger` management command.

## Objective
Turn the now-authoritative double-entry ledger into financial reporting: trial
balance, balance sheet and income statement per community/fund, statements of
account, and auditor-grade exports. Trivial once Phase 0 is done; impossible before.

## Work items
- [x] **P4-01** Trial balance report (global + per dimension: community/fund via
  `fund_type`/`fund_id`, op_type). `reporting.trial_balance()`.
- [x] **P4-02** Balance sheet & income statement from GL classifications
  (ASSET/LIABILITY/EQUITY/INCOME/EXPENSE). `balance_sheet()` enforces
  Assets = Liabilities + Equity + retained earnings; `income_statement()`.
- [x] **P4-03** Member/group statement of account (opening balance, period lines
  with running balance, closing balance) from `JournalLine`. `statement_of_account()`.
- [x] **P4-04** Immutable audit export (CSV via `export_ledger`, JSON via
  `/reports/export/`) of journals + lines.
- [ ] **P4-05** Read-model/materialised views for heavy reports — deferred;
  raw-line aggregation is fast enough at current scale (raw lines stay the truth).
- [ ] **P4-06** Scheduled close/period snapshots — deferred.

## API (staff / `IsAdminUser`)
- `GET /api/ledger/reports/trial-balance/?as_of=&fund_type=&fund_id=&op_type=`
- `GET /api/ledger/reports/balance-sheet/?as_of=&fund_type=&fund_id=`
- `GET /api/ledger/reports/income-statement/?start=&end=&fund_type=&fund_id=`
- `GET /api/ledger/reports/statement/?account=<code>` (or `?fund_type=&fund_id=&user_id=`)
- `GET /api/ledger/reports/export/?start=&end=`

## Acceptance criteria
- [x] Reports reconcile to the ledger to the cent; global trial balance is zero.
- [x] Statements are reproducible from immutable lines at any past point in time (`as_of`).

## Exit criteria
- [x] Financial statements per community/fund (fund_type/fund_id filters; staff
  API today — community-admin-scoped self-serve is a follow-up enhancement).
- [x] Auditable export pipeline (`export_ledger` CSV + JSON endpoint).
