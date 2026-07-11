# ADR-0030: De-couple the ledger from the M-Pesa adapter

- **Status:** Accepted
- **Date:** 2026-07-11
- **Deciders:** Architecture review
- **Convergence:** CV-23 (issue #159), enforced by CV-11 (#160)
- **Relates to:** [ADR-0005](0005-payment-provider-abstraction.md) (payment port), [ADR-0002](0002-remove-legacy-ledger-and-mutable-balances.md)

## Context
The handbook's cardinal structural rule is that **the ledger depends on nothing
above it and knows nothing of any payment rail** (Module-Boundaries Rule 1; P-18).
The code had drifted from this: `apps/ledger/tasks.py` imported `apps.mpesa`
directly in three places —

1. a **dead** `from apps.mpesa.services import MpesaService` (the payout
   initiation already routes through `get_provider().initiate_payout()`, so the
   import was unused);
2. `from apps.mpesa.views import _on_b2c_success`, reached only inside
   `if safaricom_state == "SUCCESS"` — a branch that is **unreachable**, because
   the stale-recovery status probe (`_query_safaricom_status`) only ever returns
   `"UNKNOWN"`; and
3. `_query_safaricom_status` itself, which builds a raw **Daraja
   `TransactionStatusQuery`** — genuine rail orchestration living inside the
   ledger.

The `PaymentProvider` port ([ADR-0005](0005-payment-provider-abstraction.md))
already exists and already carries `initiate_payout` / `query_status`, so the
ledger had a sanctioned rail-agnostic seam it was bypassing.

## Decision
Sever every `apps.mpesa` import from `apps/ledger`, behaviour-preservingly:

1. **Remove the dead `MpesaService` import.**
2. **Move the Daraja status re-query behind the port.** Add an optional,
   best-effort `PaymentProvider.request_payout_result(provider_ref)` (default
   no-op; `MpesaProvider` implements it with the Daraja `TransactionStatusQuery`
   that previously lived in the ledger; `FakeProvider` inherits the no-op). The
   ledger's `_query_safaricom_status` now calls the port and, as before, returns
   `"UNKNOWN"`.
3. **Delete the unreachable success branch** (and with it the
   `apps.mpesa.views._on_b2c_success` import). Behaviour is unchanged because the
   branch never executed.
4. **Enforce it:** a CI guard fails the build if anything under `apps/ledger`
   imports `apps.mpesa`.

The ledger now only *records* confirmed money and asks the **port** to move it —
never the adapter.

## Consequences
- **+** `apps.ledger` imports nothing from `apps.mpesa`; the cardinal boundary
  holds and is machine-enforced.
- **+** Daraja `TransactionStatusQuery` orchestration moves into the adapter where
  it belongs.
- **+** No behaviour change: the initiate path already used the port; the deleted
  branch was unreachable; the re-query is a faithful move.
- **−** Two known items remain, tracked as follow-ups (not silently deferred):
  - **Daraja vocabulary in the ledger *model*** — `FinancialTransaction`'s
    `mpesa_checkout_id` / `mpesa_conversation_id` / `mpesa_receipt` fields. This is
    *vocabulary*, not an import; renaming them to rail-agnostic names is a
    migration-bearing change scoped as CV-23 increment 2.
  - **Latent stale-recovery limitation** — tier-2 recovery cannot *confirm* a late
    success before it force-fails + reverses (the re-query is async and the FT is
    already terminal by the time any result returns). Pre-existing; a synchronous
    payout-status check is a separate fix, not part of this de-coupling.

## Alternatives considered
- **Move the whole recovery task into `apps/payments`:** rejected for now — it is a
  Beat-scheduled task, so moving it changes the task path referenced by
  `CELERY_BEAT_SCHEDULE` and risks in-flight/queued tasks across a deploy. The port
  seam achieves de-coupling without that operational risk.
- **Repurpose `query_status` for the B2C re-query:** rejected — `query_status` is
  the generic status poll (STK-oriented in the adapter today); the async B2C
  re-request has different semantics, so it gets its own clearly-named,
  optional method.
- **Leave it and just add the guard:** impossible — the guard cannot go green while
  the imports remain; severing them is the prerequisite.
