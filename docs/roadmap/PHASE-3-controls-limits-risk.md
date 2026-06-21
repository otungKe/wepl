# Phase 3 — Controls: Limits & Risk

**Status:** 🟡 In progress · **Depends on:** Phase 0 (single posting chokepoint) · **ADR:** [0007](../adr/0007-controls-at-posting-chokepoint.md)

Implemented in `apps/controls/`: a config-driven `LimitRule` engine and an
append-only `ControlDecision` audit log, enforced from a single pre-posting hook
in `post_journal()`. Amount/count caps per scope (global / per-user), direction
(pay-in / pay-out), op_type and period (per-txn / hour / day / week / month),
with action DENY (→ `LimitExceeded`, HTTP 422) or HOLD (→ `ControlHeld`, HTTP
409). Seed defaults with `python manage.py seed_controls`.

## Objective
With `post_journal()` as the single money door, add a **controls layer** that every
value movement passes through: limits enforcement and a basic risk/velocity gate.
This is the capability that separates a finance *app* from a finance *platform*.

## Work items
- [x] **P3-01** Limits engine: per-user / global, per-op_type, per-period caps
  (txn/hour/day/week/month) for pay-ins and pay-outs. Config-driven (`LimitRule`),
  tenant-aware later. *(`apps/controls/engine.py`, `models.py`)*
- [x] **P3-02** Pre-posting hook in `post_journal()` that evaluates limits and
  rejects with a typed error (`LimitExceeded` → 422) before any journal is written.
- [x] **P3-03** Velocity check: payout count per rolling hour produces a HOLD
  decision (`ControlHeld` → 409). New-recipient / duplicate-burst heuristics: TODO.
- [x] **P3-05** Audit log of every control decision (`ControlDecision`:
  allow/deny/hold + reason + window totals), queryable + read-only in admin.
- [ ] **P3-04** Manual review **queue + `HELD` state on `FinancialTransaction`**.
  Interim: HOLD decisions are recorded and queryable (admin) but the movement is
  blocked, not parked on the FT. Durable deny/hold audit on caller rollback also
  pending (route through a separate connection / outbox).

## Acceptance criteria
- [x] A payout exceeding a configured limit is rejected before posting, with a clear error.
- [x] Control decisions are recorded and queryable.
- [x] Controls are evaluated in exactly one place (the posting chokepoint).

## Exit criteria
- [x] Limits + velocity gate live on all money paths via the single chokepoint.
- [ ] Held-transaction review workflow operational (`HELD` FT state — P3-04).
