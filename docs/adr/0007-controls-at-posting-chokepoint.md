# ADR-0007: Limits & risk controls live at the posting chokepoint

- **Status:** Accepted (implemented in `apps/controls/`, P3-01→05; P3-04 is the durable
  `HeldMovement` review queue rather than a state on `FinancialTransaction`, because a
  control exception rolls that row back. Since ADR-0033 the gate is *registered into*
  `apps/ledger/chokepoint.py` by `ControlsConfig.ready()` rather than imported by
  `post_journal`: the enforcement point is unchanged and still singular, but the ledger
  no longer depends on the controls app.)
- **Date:** 2026-06-19
- **Phase:** 3 (depends on ADR-0004)

## Context
Once `post_journal()` is the single money door (ADR-0004), controls have an obvious,
singular home. Today there are no limits, velocity checks, or fraud controls at all.

## Decision
Implement limits and risk evaluation as a **pre-posting control layer** invoked by
the posting path. A movement is evaluated (per-user/group/op_type/period limits +
velocity/anomaly checks) and either allowed, rejected with a typed error, or held
for manual review (`FinancialTransaction` state `HELD`). Every decision is audited.

## Consequences
- **+** Uniform enforcement; impossible to bypass by using a different code path.
- **+** Single audit point for compliance (Phase 8).
- **−** Adds latency to the posting path; mitigated by fast-path config caching.

## Alternatives considered
- *Controls in each service:* rejected — dispersal and bypass risk, the exact
  problem the chokepoint removes.
