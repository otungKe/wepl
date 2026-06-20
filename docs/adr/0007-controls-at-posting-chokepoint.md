# ADR-0007: Limits & risk controls live at the posting chokepoint

- **Status:** Proposed
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
