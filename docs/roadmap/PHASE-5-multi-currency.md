# Phase 5 — Multi-Currency

**Status:** 🟢 Done (core) · **Depends on:** Phase 0 (Money type), Phase 4

Currency awareness is now real end-to-end: journals balance per currency, an
effective-dated `ExchangeRate` table + `apps/ledger/fx.py` handle explicit
conversion, cross-currency settlements post a per-currency-balanced FX journal,
and reporting has a per-currency trial balance.

## Objective
Move from KES-only to multi-currency. `Account.currency` already exists; this phase
makes it real: per-currency balancing, FX handling, and currency-safe reporting.

## Work items
- [x] **P5-01** Single-currency-per-journal balancing enforced in `post_journal()`
  (Σdebit == Σcredit **per currency**). Cross-currency moves post via
  `fx.conversion_lines()` using per-currency FX clearing accounts so each currency
  squares. (FX gain/loss recognised on clearing revaluation — see notes.)
- [x] **P5-02** `ExchangeRate` model — effective-dated rates; `fx.get_rate()`
  resolves the rate effective at a time and inverts the pair when needed.
- [x] **P5-03** Currency-aware `Money` arithmetic (no implicit cross-currency math;
  ADR-0003) + explicit `fx.convert()`.
- [x] **P5-04** Per-currency trial balance (`reporting.trial_balance_by_currency`)
  and `reporting.present_value()` for consolidation at a presentation rate.
- [x] **P5-05** Currency is config-driven (`DEFAULT_CURRENCY` /
  `PRESENTATION_CURRENCY` settings); `Money` default stays KES. Remaining stray
  display-only `KES` strings in clients are cosmetic follow-ups.

## API (staff)
- `GET /api/ledger/reports/trial-balance-by-currency/?as_of=&fund_type=&fund_id=`

## Acceptance criteria
- [x] A cross-currency settlement posts a balanced, currency-correct journal incl. FX.
- [x] Trial balance holds per currency.

## Exit criteria
- [x] Multiple currencies supported end-to-end with FX accounting (per-currency
  balancing, effective-dated rates, explicit conversion, per-currency reporting).

## Notes / follow-ups
- Realised FX gain/loss: clearing-account positions are revalued/netted against a
  dedicated FX gain/loss account on a periodic close (recipe documented; the
  account + revaluation job is a follow-up).
- Consolidated balance sheet / income statement at a presentation rate can be
  built on `present_value()` (per-currency report + conversion).
