# Phase 3 — Controls: Limits & Risk

**Status:** 🟢 Done (core) · **Depends on:** Phase 0 (single posting chokepoint) · **ADR:** [0007](../adr/0007-controls-at-posting-chokepoint.md)

> Both exit criteria met. Remaining P3-03 anomaly heuristics (new-recipient,
> duplicate-amount bursts) and auto-replay-on-release are tracked as future
> enhancements, not blockers.

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
- [x] **P3-04** Manual review **queue** for blocked movements (`HeldMovement`):
  HOLD and DENY movements are recorded durably by the DRF exception handler
  *after* the service's `@transaction.atomic` rolls back (this also resolves the
  earlier deny/hold-audit durability gap), with admin **Release / Reject**
  actions and a full context snapshot. Design note: held movements are tracked as
  `HeldMovement` records rather than a `HELD` state on `FinancialTransaction` —
  money services post atomically, so a held movement's FT rolls back and there is
  no committed FT to mark. Auto-replay on release is a follow-up; release clears
  the hold so a re-initiated action proceeds.

## Acceptance criteria
- [x] A payout exceeding a configured limit is rejected before posting, with a clear error.
- [x] Control decisions are recorded and queryable.
- [x] Controls are evaluated in exactly one place (the posting chokepoint).

## Exit criteria
- [x] Limits + velocity gate live on all money paths via the single chokepoint.
- [x] Held-transaction review workflow operational (`HeldMovement` queue — P3-04).
