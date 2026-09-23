# ADR-0032: Payout orchestration belongs to payments, not the ledger

- **Status:** Accepted (2026-09-18)
- **Date:** 2026-09-18
- **Deciders:** Money-movement architecture review
- **Relates to:** enforces Module-Boundaries Rule 1 / P-18; sits on the
  `PaymentProvider` port (ADR-0005); preserves the settlement contract
  (ADR-0028); closes the orchestration half of #159. The remaining half —
  Daraja vocabulary in `FinancialTransaction`'s columns — is left to the
  `FinancialTransaction` decomposition (ADR-0030).

## Context

The cardinal rule of the layering is that **the ledger depends on nothing above
it and knows nothing of a payment rail.** It is the book of record: it posts
journals, derives balances, and proves the trial balance is zero. It should have
no opinion about M-Pesa.

`apps/ledger/tasks.py` broke that rule in the most sacred module. Alongside
`reconcile_ledger` it carried the whole outgoing-payment execution engine:

- `execute_b2c_payout` — the Celery task that dispatches a B2C payment, owns the
  PENDING → PROCESSING transition, the double-send guards, the retry budget and
  the `PaymentIntent` record.
- `recover_stale_processing_transactions` — the beat sweep that re-drives
  payouts stuck in PROCESSING.
- `_query_safaricom_status` — a hand-rolled Daraja `TransactionStatusQuery`,
  built inline from `settings.MPESA_*` and posted with `requests`, reached
  through a direct `from apps.mpesa.services import MpesaService`.
- `_handle_payout_failure` — the terminal-failure path that emits
  `payment.failed`.

So the ledger imported the rail adapter, spoke Daraja's wire vocabulary, and
orchestrated a network call. This is drift rather than an original design
choice: the app layout was right, but the invariant was never mechanized, so it
eroded one helper at a time.

Two things made the drift expensive rather than merely untidy. First, the
`PaymentProvider` port (ADR-0005) exists precisely so a second rail can be added
without touching money-path code — but a rail-specific query living in the
ledger is invisible to that port, so adding a rail would have meant editing the
ledger. Second, this is the code the `FinancialTransaction` decomposition
(ADR-0030) has to move anyway; leaving it in the ledger would have put that
slice's largest change in the module with the strictest coverage gate and the
least business to be there.

## Decision

**Payout orchestration moves to `apps/payments/payouts.py`, behind the
`PaymentProvider` port. The ledger keeps only book-keeping.**

1. `execute_b2c_payout` moves and is renamed **`execute_payout`** — nothing about
   it was B2C-specific except the rail it happened to call. Its guards, state
   machine, retry budget and `PaymentIntent` recording are unchanged.
2. `recover_stale_processing_transactions`, `_handle_payout_failure` and the
   status requery move with it. `apps/ledger/tasks.py` is left with
   `reconcile_ledger` and its alerting helper.
3. The Daraja `TransactionStatusQuery` moves into `MpesaProvider` as a new
   **optional port method, `request_payout_result()`**. It is deliberately
   separate from `query_status()`, which polls a *collection*: Safaricom answers
   a payout requery **asynchronously**, re-firing the result callback rather
   than returning the outcome, so the adapter reports `state='unknown'` and
   `B2CResultView` still finalises the payout. Adapters with no such facility
   inherit a no-op default, which leaves recovery to its own timeout — the same
   behaviour `FakeProvider` produced before, when the query blew up on missing
   credentials and was caught as `UNKNOWN`.
4. **A CI guard makes the boundary mechanical.** The build fails if anything
   under `apps/ledger` mentions `apps.mpesa`. The invariant that eroded is now
   the one thing that cannot erode silently.

Task names change with the module, so both old names are kept as thin shims that
re-queue onto the new tasks. In-flight messages and any stale
`django-celery-beat` row survive the deploy window; the tasks' own guards make a
re-queue safe. An exact-name Celery route keeps the payout tasks on the
`financial` queue, so the `apps.payments.tasks.*` glob cannot pull them onto
`payments`.

## Consequences

**Good.** `apps.ledger` imports no rail and the grep proves it. A second rail is
now an adapter change only. The settlement contract of ADR-0028 is untouched —
discovery still emits `payment.settled` / `payment.failed` and the inline
consumer still propagates. The ADR-0030 slice that has to move this code finds
it already moved, out of the coverage-gated ledger core.

**Costs.** One deploy window in which two task names are live; the shims are
deletable once the queues have drained.

When this was written, `apps/payments/payouts.py` still read
`FinancialTransaction.mpesa_conversation_id` — the rail vocabulary left in the
ledger *model*, and the other half of #159. Renaming those columns would have
been a migration written to be thrown away, since ADR-0030 planned to remove
them outright; that removal has since landed (`ledger.0021`), so the
correlation id now lives on the `PaymentIntent` and the ledger carries no
Daraja vocabulary at all.

**Not addressed.** The pre-existing stale-recovery limitation recorded against
ADR-0028 stands: because the requery is asynchronous, tier-2 recovery cannot
confirm a late success before it force-fails and reverses. Moving the code
neither fixes nor worsens it.
