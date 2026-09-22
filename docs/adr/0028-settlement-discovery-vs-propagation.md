# ADR-0028: Settlement — discovery vs propagation

- **Status:** Accepted (2026-09-17)
- **Date:** 2026-09-17
- **Deciders:** Money-movement architecture review
- **Relates to:** builds on the outbox (ADR-0006) and the payment aggregate
  (ADR-0014); consumes the generalized event log (ADR-0029) as its delivery
  substrate; is the settlement contract the `FinancialTransaction` decomposition
  will be built against.

## Context

When an external payment rail settles — a B2C payout lands, an STK collection
clears — two different jobs have to happen, and today's code runs them **as one
inseparable blob, duplicated at every place the settlement might be observed.**

Trace a payout finalization. The exact same three-step sequence — *reverse-or-
confirm the ledger, advance the business workflow, notify* — is written out
three times:

- **`apps/payments/views_mpesa.py`, `B2CResultView`** — the Daraja B2C result callback. On success:
  `on_payout_settled(ft, receipt)` (:413). On failure:
  `reverse_financial_transaction(ft, ...)` then `on_payout_failed(ft)` (:427-428).
- **`apps/ledger/tasks.py:204-341`** — the `execute_b2c_payout` task. On a
  synchronous success it calls `on_payout_settled(ft, receipt)` (:206); on failure
  it calls `reverse_financial_transaction(ft, ...)` then `on_payout_failed(ft)`
  (:331, :341).
- **`apps/payments/ops.py:186-210`** — the operator recovery path. Success:
  `on_payout_settled(ft, "")` (:192); failure: `reverse_financial_transaction`
  then `on_payout_failed(ft)` (:203-210).

Three copies of the finalization recipe, each reached by a **different observer**
of the same fact. This is not accidental duplication that a refactor would tidy
away — it is the symptom of a conflation. Two genuinely distinct concerns are
fused:

1. **Discovery** — *"did the rail actually settle, and how?"* This is inherently
   **multi-source**. A rail's callback is best-effort: it can arrive late, arrive
   twice, or never arrive. So discovery legitimately has three independent
   witnesses — the callback (`payments/views_mpesa.py`), the requery/timeout sweep
   (`recover_stale_processing_transactions`, `apps/ledger/tasks.py:157`;
   `reconcile_payments`, `apps/payments/reconciliation.py`), and the human
   operator (`apps/payments/ops.py`). You cannot collapse these into one; removing
   any of them loses a class of stuck money. Multi-source discovery is **correct**.

2. **Propagation** — *"now make that fact true everywhere in the system."* This is
   the reverse-or-confirm-the-ledger + advance-the-domain + notify sequence. It
   should happen **exactly once per settlement, from one place**, no matter which
   witness discovered the fact. Today it is copied into each witness, so every new
   witness re-implements it and any change to the recipe must be made in three
   files that can silently drift.

The conflation also opens a **correctness gap**. `recover_stale_processing_
transactions` (`apps/ledger/tasks.py:157-179`) only sweeps FTs in state
`PROCESSING`. If a payout reaches a terminal state on the rail but propagation
never completes — the callback dispatch dies after the FT is marked `SUCCESS` but
before `on_payout_settled` finishes — the FT is no longer `PROCESSING`, so the
sweep skips it, and only an operator poking `apps/payments/ops.py` will ever catch
it. There is no durable "this settlement's propagation is owed" record; propagation
is a side effect of whichever code path happened to observe the settlement, so if
that path dies mid-way the work is simply lost.

The outbox we already have (ADR-0006) is the right substrate for once-only
propagation — but it cannot carry this today, for three concrete reasons:

- **`emit()` is frozen into a notification shape.** Its signature
  (`apps/core/events.py:35-39`) is
  `emit(event_type, *, user_id, title, message, community_id=None,
  conversation_id=None, contribution_id=None, join_request_id=None)`. There is
  nowhere to put `payment.settled{ft_id, amount, receipt}`; the payload is
  user-facing notification fields plus business FK hints, not a general domain
  event. A settlement event does not have a `user_id`/`title`/`message` and should
  not be forced to invent them.
- **All consumers share one transaction.** `process_outbox`
  (`apps/core/tasks.py:36-72`) claims events with
  `select_for_update(skip_locked=True)` and fans out with a plain
  `domain_event.send(...)` (:58) inside a single `transaction.atomic()` (:44) per
  batch. `send` (not `send_robust`) means one consumer raising aborts the shared
  transaction and rolls back the others' work. That is the correct failure mode for
  a notification (retry the batch) and the **wrong** one for money: a financial
  posting consumer must not be able to roll back — or be rolled back by — a
  notification consumer.
- **No per-aggregate ordering or dedup contract.** The relay orders by outbox row
  id globally, not per subject, and dedup is each consumer's private business
  (`Notification.event_id`). Money propagation needs a defined answer to "what is
  the ordering key" and "what is the dedup key" — otherwise a late duplicate
  `payment.settled` could double-post.

## Decision

**Split settlement into discovery and propagation, and give each the shape it
actually needs.**

### 1. Discovery stays multi-source; its only job is to record the fact

The callback (`payments/views_mpesa.py`), the requery/timeout sweep (`ledger/tasks.py`,
`payments/reconciliation.py`), and the operator (`payments/ops.py`) all remain.
Each is a witness that may independently observe "the rail settled." A witness
does **not** run the finalization recipe. Its sole responsibility is to durably
record the discovered fact **once** — emit a single settlement domain event
(`payment.settled` / `payment.failed`) into the outbox, idempotently keyed so that
a second witness observing the same settlement is a no-op, not a second event.

### 2. Propagation moves to one durable event, consumed once

The reverse-or-confirm-ledger + advance-domain + notify recipe stops being inline
code at each witness. It becomes the set of **consumers** of the settlement event:

- a **ledger** consumer that confirms or reverses the posting,
- the owning **business context** consumer that advances its workflow,
- a **notification** consumer.

Each is idempotent on the settlement event's key. Whichever witness discovered the
fact, propagation runs exactly once, from one place, and — critically — is now a
**durable obligation**: an unconsumed settlement event is a visible, retryable
outbox row, closing the "SUCCESS-but-unfinalized" gap that the `PROCESSING`-only
sweep leaves open today.

### 3. Three prerequisites, in order

This decomposition is not free; it depends on three changes to the eventing
substrate, and they must land before (or with) the settlement event. Prerequisites
1 and 2 are specified in **ADR-0029 (generalized outbox event log)**, which this
ADR consumes as its delivery substrate:

1. **Generalize the outbox payload beyond the notification shape.** A domain event
   is `(event_type, aggregate, payload: JSON primitives)`. Notification fields
   (`title`/`message`/`user_id`) become the payload of *notification* events, not a
   mandatory part of every event's signature. `emit()`'s current callers
   (~30 sites, ADR-0006) keep a compatible notification helper; money events use
   the general form.
2. **Isolate financial consumers from notification consumers.** A financial
   propagation consumer must not run in the same transaction as, or be able to be
   rolled back by, a notification consumer. Delivery moves to `send_robust`-style
   per-consumer isolation (or separate relay lanes), so one consumer's failure
   neither aborts the others nor blocks their retries. This is the change that
   makes the outbox safe for money, not just for notifications.
3. **Define ordering and dedup semantics per aggregate.** The settlement event
   declares its **dedup key** (so a duplicate late callback is a no-op) and its
   **ordering key** is the aggregate, not the global row id (so two events for the
   *same* payment are ordered, while unrelated payments are not serialized behind
   each other).

### 4. Discovery and propagation are complementary, not alternatives

This ADR explicitly rejects the framing of "outbox **vs** idempotent-multi-source."
Both are kept. Multi-source **discovery** is why money never gets stuck unseen;
once-only durable **propagation** is why the observed fact is applied correctly and
exactly once. The bug today is that they were fused; the fix is to separate them,
not to pick one.

## Consequences

- **+** The finalization recipe exists **once** (as consumers), not three times
  (`payments/views_mpesa.py`, `ledger/tasks.py`, `payments/ops.py`).
  A new witness (a second rail's callback, a new sweep) emits the same event and
  gets correct propagation for free; changing the recipe is a one-file change.
- **+** Propagation becomes a **durable obligation** (an outbox row), not a side
  effect of a live code path — closing the SUCCESS-but-unfinalized gap the
  `PROCESSING`-only sweep (`ledger/tasks.py:157`) leaves open.
- **+** The generalized, consumer-isolated outbox fixes Core's "events know too
  much" smell (ADR-0006's own note that `emit()` is notification-specific) and is
  the substrate for Phase 7 outbound webhooks — one change, two payoffs.
- **+** This is the **written contract the `FinancialTransaction` decomposition
  builds against**: FT can dissolve into a ledger posting envelope, a payments
  rail-lifecycle aggregate (ADR-0014's `PaymentIntent`), and per-context workflows
  precisely because settlement propagation is choreographed by one durable event
  rather than by an FT god-object that every witness mutates directly.
- **−** The eventing substrate must change before the payoff lands: a general event
  shape, per-consumer isolation, and a stated ordering/dedup contract. Until then
  the triplicated finalization stays.
- **−** Two-phase discovery→propagation is more moving parts than an inline call;
  an unconsumed settlement event is a new thing that must be monitored (it is also
  a new thing that *can* be monitored — today the lost work is invisible).
- **−** Consumers must be genuinely idempotent on the settlement key. This is
  already required by ADR-0006's at-least-once contract, but money makes a latent
  requirement load-bearing.

## Alternatives considered

- **Keep multi-source finalization, just extract the shared recipe into a helper.**
  Rejected as insufficient — a shared function still runs *inside* each witness's
  code path, so propagation dies with that path (the SUCCESS-but-unfinalized gap
  remains) and there is still no durable "propagation owed" record. The recipe must
  become a *consumed durable event*, not a called function.
- **Make one witness authoritative (e.g. only the callback finalizes).** Rejected —
  the callback is best-effort (late/duplicate/absent), which is exactly why the
  requery sweep and operator paths exist. Removing witnesses loses stuck money;
  discovery must stay multi-source.
- **Emit the settlement event through the existing `emit()`.** Rejected — its
  signature (`apps/core/events.py:35-39`) is notification-shaped; forcing a
  settlement through it means inventing a `title`/`message`/`user_id` for a money
  fact and routing it through a fan-out that shares one transaction with
  notification consumers (`apps/core/tasks.py:44-58`). Prerequisites 1 and 2 exist
  to remove exactly this.
- **Drive propagation off the FT state machine directly (status-change hook).**
  Rejected — it re-centralizes money movement on the FT god-object this line of
  work is dissolving, and couples the financial core to every consuming business
  context. The event decouples them.
- **Skip the durable event; rely on `reconcile_payments` to repair drift after the
  fact.** Rejected — reconciliation is a safety net for detecting divergence, not a
  primary propagation mechanism; making it primary means every settlement is
  "wrong until the next hourly sweep repairs it," which is unacceptable for member-
  visible money movement.
