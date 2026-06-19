# Phase 5 — Multi-Currency

**Status:** 🔴 Not started · **Depends on:** Phase 0 (Money type), Phase 4

## Objective
Move from KES-only to multi-currency. `Account.currency` already exists; this phase
makes it real: per-currency balancing, FX handling, and currency-safe reporting.

## Work items
- **P5-01** Enforce single-currency-per-journal balancing; cross-currency moves use
  an FX journal with a dedicated FX gain/loss account.
- **P5-02** Exchange-rate source + rate table with effective-dated rates.
- **P5-03** Currency-aware `Money` arithmetic (no implicit cross-currency math).
- **P5-04** Per-currency trial balance; consolidated reporting at a presentation rate.
- **P5-05** Remove remaining KES/`Africa/Nairobi` hardcoding outside config.

## Acceptance criteria
- A cross-currency settlement posts a balanced, currency-correct journal incl. FX.
- Trial balance holds per currency.

## Exit criteria
- [ ] Multiple currencies supported end-to-end with FX accounting.
