# ADR-0014: Provider-agnostic Payment aggregate & reconciliation

- **Status:** Accepted (aggregate + reconciliation implemented; provider-statement leg & reversals deferred)
- **Date:** 2026-06-24
- **Relates to:** Platform Hardening Review §2.6 + Action Plan P2 #12; builds on the provider port (ADR-0005).

## Context

The rail port (ADR-0005) is the right shape, and `mpesa` is solid, but money
orchestration is **M-Pesa-shaped**: the ledger `FinancialTransaction` carries
`mpesa_*` columns, and there was no provider-agnostic record of an external
payment's lifecycle. The review also flagged the absence of real reconciliation
(provider ↔ intents ↔ ledger) with drift alerting. The `payments` app's service
layer was an empty stub.

## Decision

### A provider-agnostic `PaymentIntent` aggregate
A new `payments.PaymentIntent` captures one **attempt to move money through a
provider**, keyed by `(provider, provider_ref)`, with a small lifecycle:
`PENDING → SUCCEEDED | FAILED`, and `SUCCEEDED → REVERSED`. It links (nullably) to
the ledger `FinancialTransaction`, which remains the internal money-op + journal
anchor. The intent decouples the *external* payment view from the rail's wire
details, so a second provider (card/bank) slots in by feeding the same aggregate.

`PaymentService` owns the state machine: `record_initiation` (idempotent on an
`idempotency_key`) and `resolve(provider, provider_ref, success)` (idempotent — a
duplicate or late callback on a terminal intent is a no-op).

### Fed at the provider chokepoints (strangler)
The aggregate is populated **best-effort** at the four port chokepoints — STK
collection initiate, B2C payout initiate, and both callbacks — each wrapped so a
payment-bookkeeping error can never break the money path (the ledger stays the
source of truth). This mirrors the P0-05 "post alongside" strangler used for the
ledger itself; the intent is a parallel source of truth now and can become
authoritative later.

### Reconciliation
`reconcile_payments` (hourly Celery beat) cross-checks the views and opens a
`ReconciliationDrift` row (deduped per open subject; read-only admin with a
resolve action; `WARNING` log as the alert seam) for:
- intents stuck `PENDING` past a grace window,
- intent ↔ FT terminal-state mismatch (where linked),
- a `SUCCESS` FT with no posted journal entry (ledger linkage broken),
- an FT stuck in `PROCESSING` past a grace window.

## Consequences

- **+** A rail-agnostic seam for the payment lifecycle — multi-provider readiness.
- **+** Live, queryable reconciliation over the intent↔FT↔ledger legs with drift triage.
- **+** No behaviour change / no risk to the proven mpesa flow (best-effort wiring).
- **−** The intent is not yet authoritative (parallel record); callers still drive
  the FT directly.

## Deferred (documented)

- **Provider-statement leg** of reconciliation (fetch the rail's settlement file via
  the Daraja transaction-query API) for a *true* three-way match.
- **Reversals/settlements** as first-class flows (a refund as a ledger reversal +
  provider refund, transactionally linked) — `REVERSED` exists on the aggregate but
  isn't yet driven end-to-end.
- **Generic signed-webhook intake** (raw-body store + signature verify + dedupe)
  generalising the mpesa callback for future providers.
- Migrating callers onto the aggregate as the authoritative record.

## Alternatives considered

- **Extend `FinancialTransaction` with a generic `provider`/`provider_ref`** instead
  of a new model. Rejected: FT is the *internal* money-op (and already M-Pesa-shaped);
  a separate external aggregate keeps the provider lifecycle from further polluting
  the ledger core and lets one money-op span multiple provider attempts.
- **Reuse the legacy contribution-coupled `payments.Payment`.** Rejected — it's tied
  to `Contribution` and unused since manual recording was removed.
