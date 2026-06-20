# ADR-0003: Money representation — Decimal(20,4) + Money value object + currency

- **Status:** Accepted
- **Date:** 2026-06-19
- **Phase:** 0 (P0-03)

## Context
Monetary precision is inconsistent: legacy fields use `Decimal(12–14, 2)` while the
double-entry core uses `Decimal(20, 4)`. Mixed precision across a reconciliation
boundary is a latent rounding/drift hazard. Amounts are also passed around as bare
`Decimal`/`str`/`float`-via-`str` with no currency attached.

## Decision
- All monetary columns standardise on **`Decimal(20, 4)`** with an explicit
  **`currency`** (default `KES`).
- Introduce a **`Money`** value object (amount + currency) used at service
  boundaries; no implicit cross-currency arithmetic.
- One documented rounding policy (**banker's rounding**, `ROUND_HALF_EVEN`),
  applied at well-defined quantisation points only.

## Consequences
- **+** Single precision everywhere; currency-safe arithmetic; ready for Phase 5.
- **+** Eliminates `float`-adjacent handling.
- **−** A data migration to widen/realign legacy columns (cheap pre-production).

## Alternatives considered
- *Integer minor units (cents):* viable and common, but `Decimal(20,4)` already
  used by the core and supports sub-cent rail fees; revisit if perf demands.

## Implementation status (2026-06-19)
`apps/ledger/money.py` implements the `Money` value object: `Decimal(20,4)`
normalisation, `ROUND_HALF_EVEN` via a single `quantize()` entry point, 3-char
currency (default `KES`), currency-safe arithmetic/ordering (cross-currency
raises `CurrencyMismatch`), and `allocate`/`split` that lose no minor units.
Covered by 24 tests and gated in CI. Column-precision alignment for surviving
config columns lands with the money-path rewrite (P0-05); legacy balance columns
are deleted rather than migrated (ADR-0002).
