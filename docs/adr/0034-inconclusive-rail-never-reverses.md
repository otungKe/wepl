# ADR-0034: An inconclusive rail never reverses a payout

- **Status:** Accepted (2026-09-26)
- **Date:** 2026-09-26
- **Deciders:** Money-path review — stale-payout recovery
- **Relates to:** resolves the "Not addressed" limitation recorded against
  ADR-0028 (settlement discovery vs propagation) and restated in ADR-0032
  (payout orchestration in payments); relies on ADR-0005's provider port for the
  rail's status facility and on ADR-0002's derived-truth rule for why a wrong
  reversal is not repairable by patching a balance.

## Context

`recover_stale_processing_transactions` (`apps/payments/payouts.py`) is one of
ADR-0028's three settlement witnesses: the timeout sweep that exists so money
never sits stuck unseen. Past a 60-minute horizon it asked the rail for the
payout's outcome and then, on anything other than a confirmed success, forced the
`FinancialTransaction` to `FAILED` and emitted `payment.failed`, whose consumer
posts the reversing journal and resets the domain object.

The defect was in what counted as "anything other than success". The helper
returns three values — `SUCCESS`, `FAILED`, `UNKNOWN` — and the sweep treated
`FAILED` and `UNKNOWN` identically. For the only live payout rail, `UNKNOWN` is
the *only* value obtainable: Daraja's `TransactionStatusQuery` is asynchronous, so
`MpesaProvider.request_payout_result` accepts the query and reports `unknown`
while Safaricom re-fires the real answer to the B2C `ResultURL`. The
`== "SUCCESS"` branch was therefore unreachable in production and every payout
still `PROCESSING` after an hour was reversed, whether or not the money had left.

Three properties made that unrecoverable rather than merely wrong:

1. **`FAILED` is terminal** (`FinancialTransaction.VALID_TRANSITIONS`). When the
   re-fired success callback lands, `B2CResultView` catches the resulting
   `TransitionError`, logs a warning and returns `200`. Nothing corrects the
   reversal; the only trace is a log line.
2. **The reversal is a real journal.** Balances are derived from immutable lines
   (ADR-0002), so the pool genuinely reads as though the money came back. There
   is no counter to quietly correct — only a further correcting journal, posted
   by someone who noticed.
3. **The domain object is reset for re-trigger**, so an admin can pay a second
   time for a payout the rail already settled.

The sweep was, in effect, resolving an unknown by assuming the outcome that
writes to the books. Its docstring described the behaviour it was intended to
have rather than the behaviour it had.

## Decision

**A witness may only propagate what the rail actually told it. An inconclusive
rail is escalated, never resolved.**

Tier-2 recovery branches on all three answers:

- **`SUCCESS`** → transition to `SUCCESS`, emit `payment.settled`. Unchanged.
- **`FAILED`** → force `FAILED`, emit `payment.failed`; the settlement consumer
  reverses. This is the case the auto-recovery was written for and it stays.
- **`UNKNOWN`** → **do nothing to the money.** The FT stays in `PROCESSING` and
  the sweep escalates.

Escalation reuses the machinery that already exists rather than adding a new
one: `backoffice/tasks.py::ops_alerts` raises a `payouts_awaiting_decision`
`StaffNotice` at **CRITICAL**, de-duplicated and auto-resolving like every other
condition it manages, and the operator resolves each movement through
`PaymentOpsService` (`payments/ops.py`) — requery, retry, reverse or mark failed,
each audited. That is a distinct condition from the existing `stuck_payouts`
WARNING: "open longer than expected" is a nudge, whereas "the automatic path has
given up and only a human can close this" is an obligation.

The sweep's return value gains `awaiting_decision`, so "parked" is a reported
outcome rather than silence.

On the M-Pesa rail the practical consequence is that **no stale payout is ever
auto-reversed.** That is the intended reading, not an oversight.

## Consequences

- **+** The books can no longer be credited for money that left the float
  without a human deciding so. The failure mode moves from "silently wrong and
  unrecoverable" to "visibly unresolved".
- **+** The failure is now *loud*: a CRITICAL notice and a Sentry event per
  condition, versus a warning line nobody reads.
- **+** ADR-0028's separation holds more strictly — a witness's job is to record
  what it observed, and "I could not observe it" is not an observation of
  failure.
- **−** Funds stay reserved in a stuck payout until an operator acts. Previously
  they were released automatically within the hour, sometimes correctly. This is
  a deliberate trade of availability for correctness: an over-held pool is
  recoverable by a human, a falsely reversed payout is not.
- **−** Operational load grows with rail flakiness: every lost callback becomes a
  queue item. The right relief is fewer lost callbacks (or a rail facility that
  answers inline), not re-arming the guess.
- **−** A payout whose callback never arrives at all stays in `PROCESSING`
  indefinitely if nobody works the queue. The notice is the mitigation; a
  hard expiry would reintroduce exactly this ADR's defect.
- **~** A parked payout is re-queried on every sweep until an operator closes it,
  so a never-answered payout costs two `TransactionStatusQuery` calls an hour
  indefinitely. That is mostly a feature rather than a cost — the query's real
  effect is to re-fire the result callback, which is the documented way these
  resolve — but it is unbounded, which is another reason the queue is meant to be
  worked rather than tolerated.

## Alternatives considered

- **Keep auto-reversing, but only after a longer horizon (24 h, a week).**
  Rejected — it lengthens the odds without changing the logic. A lost callback is
  lost regardless of how long you wait, so a long-horizon reversal is still a
  reversal on no evidence, just rarer and harder to correlate when it bites.
- **Make `FAILED → SUCCESS` a legal transition so a late callback self-heals.**
  Rejected — it makes a terminal state re-openable for every path, not just this
  one, and the reversing journal would still need a compensating entry. The
  ledger's correction mechanism is a new journal (ADR-0002); the state machine
  should not become a second one.
- **Auto-reverse, and let the hourly `reconcile_payments` sweep detect and repair
  the false reversals.** Rejected on ADR-0028's own reasoning: reconciliation is
  a net for detecting divergence, not a licence to create it. It would also mean
  a member-visible balance is wrong until the next sweep.
- **Fold this into the existing `stuck_payouts` WARNING.** Rejected — it is
  de-duplicated into one notice covering everything merely slow, so the items
  that need a decision would be invisible inside it, at the wrong severity.
- **Have the adapter poll Daraja until the status is known.** Rejected — Daraja
  answers on the callback URL and nowhere else, so there is nothing to poll. The
  callback endpoint already is the resolution path; this ADR is about what to do
  while it has not fired.
