# Phase 3 — Controls: Limits & Risk

**Status:** 🔴 Not started · **Depends on:** Phase 0 (single posting chokepoint) · **ADR:** [0007](../adr/0007-controls-at-posting-chokepoint.md)

## Objective
With `post_journal()` as the single money door, add a **controls layer** that every
value movement passes through: limits enforcement and a basic risk/velocity gate.
This is the capability that separates a finance *app* from a finance *platform*.

## Work items
- **P3-01** Limits engine: per-user, per-group, per-op_type, per-period caps
  (daily/weekly/monthly) for pay-ins and pay-outs. Config-driven, tenant-aware later.
- **P3-02** Pre-posting hook in the posting path that evaluates limits and rejects
  with a typed error (mapped to 422/429) before any journal is written.
- **P3-03** Velocity/risk checks: rapid repeated payouts, new-recipient anomalies,
  duplicate-amount bursts; produce a risk score + hold/queue decision.
- **P3-04** Manual review queue + state (`HELD`) on `FinancialTransaction`.
- **P3-05** Audit log of every control decision (allow/deny/hold + reason).

## Acceptance criteria
- A payout exceeding a configured limit is rejected before posting, with a clear error.
- Control decisions are recorded and queryable.
- Controls are evaluated in exactly one place (the posting chokepoint).

## Exit criteria
- [ ] Limits + velocity gate live on all money paths via the single chokepoint.
- [ ] Held-transaction review workflow operational.
