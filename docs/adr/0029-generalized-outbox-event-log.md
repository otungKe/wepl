# ADR-0029: Generalize the outbox from notification queue to domain event log

- **Status:** Proposed
- **Date:** 2026-09-17
- **Deciders:** Money-movement architecture review
- **Relates to:** generalizes the transactional outbox (ADR-0006); is the substrate
  prerequisite named by the settlement split (ADR-0028); shares the payment
  aggregate's boundary discipline (ADR-0014). Phase 7 outbound webhooks consume the
  same event log.

## Context

The transactional outbox (ADR-0006) is durable and correct for what it does, but
what it does is deliver **notifications**, not domain events. The shape gives it
away:

- **`emit()` hardcodes a notification payload.** Its signature
  (`apps/core/events.py:35-39`) is `emit(event_type, *, user_id, title, message,
  community_id, conversation_id, contribution_id, join_request_id)`, and the body
  it stores (`events.py:60-71`) is exactly those seven keys. `OutboxEvent.payload`
  (`apps/core/models.py:19`) is free-form JSON in principle but always holds that
  one shape. There is nowhere to put `payment.settled{ft_id, amount, receipt}`, and
  a settlement fact has no `user_id`/`title`/`message` to supply.
- **There is exactly one consumer, and it does not do work in the relay.**
  `dispatch_notification` (`apps/core/../notifications/receivers.py:18`) is the sole
  `@receiver(domain_event)`; it merely `send_notification.delay(...)`
  (`receivers.py:41`) — it enqueues a Celery task and returns. So the whole outbox
  today is a notification fan-out.
- **All consumers share one transaction and one fate.** `process_outbox`
  (`apps/core/tasks.py:44-63`) claims the oldest PENDING event and calls
  `domain_event.send(...)` — plain `.send`, not `send_robust` — inside a single
  `transaction.atomic()`, then marks the row PROCESSED in that same transaction.
  With one enqueue-only consumer this is harmless. With a *second* consumer that
  does real synchronous work — a ledger posting — it is not: one consumer raising
  aborts the shared transaction and rolls the others back, and there is no
  per-consumer retry or dead-letter. This is the correct failure mode for a
  notification (retry the batch) and the wrong one for money.
- **Dedup is on the wrong key for multi-source facts.** Consumers dedupe on
  `outbox_event_id` (→ `Notification.event_id`), which collapses *redelivery of one
  row*. It cannot collapse *two rows describing one fact* — precisely what ADR-0028
  requires, where a rail callback and the requery sweep each legitimately emit
  `payment.settled` for the same transaction.
- **Ordering is global, not per subject.** The relay orders by `order_by('id')`
  (`tasks.py:50`); there is no notion of "these two events concern the same
  aggregate and must apply in order."

ADR-0006's own implementation notes already flagged this: *"`emit()` today is
notification-specific… store `payload` as generic JSON so Phase 7 webhooks reuse
the table."* The generic table exists; the generic *contract* does not. ADR-0028
is the forcing function: settlement propagation needs a durable event this bus
cannot express, delivered to a financial consumer this relay cannot safely run.

## Decision

Generalize the outbox into a true domain event log, **staged** so the machinery
arrives only when a second consumer justifies it, and delegate money-dedup to the
ledger rather than rebuilding it here.

### 1. Envelope + typed body

Separate the routing/identity **envelope** (same for every event) from the
event-type-specific **body** (arbitrary JSON primitives):

```
envelope:  event_type, aggregate_key, dedup_key, occurred_at, schema_version
body:      { …event-type-specific JSON… }
```

The existing seven notification fields become simply the **body of
notification-shaped events** — they are not privileged, and no other event type
must carry them. `payment.settled` carries `{ft_id, amount, receipt}` and no
presentation strings.

This is the *minimal* generalization (call-site preserving), **not** the fuller
move of stripping presentation (`title`/`message`) off the bus entirely behind a
notification-policy layer. That fuller move is a Core-boundary project in its own
right; it stays reachable — a notification body is structurally just a body — and
is deliberately **out of scope here** so this ADR can unblock settlement without a
~30-call-site rewrite.

### 2. Staged rollout

- **Stage 1 — envelope only, additive, zero behaviour change.** `emit()` gains the
  envelope around the body; `OutboxEvent` gains the envelope columns; the single
  notification consumer keeps working unchanged (its body is the old seven fields).
  Delivery, ordering, and execution modes are untouched. Ships alongside ADR-0028
  as the concrete first step.
- **Stage 2 — delivery + registry + execution modes, landing *with* the first
  financial consumer** (the ADR-0028 settlement consumer). That is the first moment
  two consumers must not share a fate, so it is the moment the machinery earns its
  keep — mirroring the house strangler discipline (ADR-0014's best-effort
  "post alongside").

### 3. Per-consumer delivery rows (Stage 2)

The fix for "one consumer rolls back another" is **not** `send_robust` (which only
stops exception propagation while leaving one shared transaction and one shared
retry/dead-letter fate). It is **one delivery row per (event, consumer)** — an
`OutboxDelivery` — so each consumer acks, retries, and dead-letters independently.
A stuck notification never blocks or reverts a ledger post, and vice versa. This is
what turns the outbox from a shared queue into a per-subscriber event log.

### 4. Execution modes, declared per consumer (Stage 2)

A consumer declares how it runs; the relay honours it:

- **`inline_atomic`** (financial): runs synchronously in the relay and acks its
  delivery row in the **same transaction** as its effect. At-least-once delivery ×
  idempotent apply = exactly-once effect, with no reopened crash gap.
- **`enqueue`** (notifications): enqueues a Celery task and acks immediately;
  best-effort, dedup downstream. This is exactly today's behaviour, preserved.

Money is not forced through the notification model, nor notifications through the
money model.

### 5. Explicit subscription registry for the inline lane (Stage 2)

Today *any* `@receiver(domain_event)` silently receives *every* event type
(`receivers.py:18` filters nothing). For money that is a bug, not a feature. The
`inline_atomic` lane uses an **explicit subscription registry** — a consumer names
the event types it handles, its execution mode, and its dedup scope:

```
Subscription{ consumer_name, event_types:{…}, execution_mode, dedup_scope, handler }
```

Django signals are **kept for the `enqueue` lane** (fan-out-to-all is fine for
notifications); the registry governs only the lane where "subscribes to everything"
would be dangerous. The execution mode selects the lane.

### 6. Per-aggregate ordering (Stage 2)

`aggregate_key` (e.g. `payment:123`) orders and locks *within* an aggregate — two
events for the same aggregate apply in order — while different aggregates run in
parallel. The settlement need is modest (events are near-terminal), but it must be
**stated** so a later flow (partial capture, reversal-after-confirm) cannot reorder
silently.

### 7. Dedup delegated to the ledger — no new dedup table

`inline_atomic` consumers dedupe on the business `dedup_key`, and the durable
"have I applied fact X?" record is the consumer's **own write**: for the settlement
consumer, `dedup_key` *is* the `post_journal` `idempotency_key` (ADR-0004). The
ledger already refuses a duplicate key, so a re-delivered — or second-witness
(ADR-0028) — `payment.settled` is a no-op **at the post**, with no extra
bookkeeping. The outbox never needs its own money-dedup ledger; it stays ignorant
of what "applied" means and delegates to the door money already walks through.

Consumer-side idempotency is therefore **mandatory**; emit-time collapse (a
partial-unique index on PENDING rows) is **not** adopted — it is racy (once the
first row is PROCESSED it no longer blocks a second witness's insert) and
redundant given consumer-side dedup.

## Consequences

- **+** The bus can carry any domain fact, not just a notification — unblocking the
  ADR-0028 settlement event and Phase 7 outbound webhooks on one substrate.
- **+** Financial and notification consumers have independent fate: no shared
  transaction, no shared retry/dead-letter, no cross-consumer rollback.
- **+** Multi-source facts (ADR-0028) collapse correctly, and money-dedup reuses
  `post_journal`'s existing idempotency guarantee rather than reinventing it — the
  cleanest seam between the outbox and the financial core.
- **+** Staging means Stage 1 is a safe additive change and no speculative
  machinery is built before a second consumer justifies it.
- **+** Notification behaviour is preserved exactly (the `enqueue` lane over
  signals is today's path).
- **−** Two lanes (registry-driven inline, signal-driven enqueue) is more concept
  than a single fan-out; the registry is a new surface consumers must register in.
- **−** Stage 2 adds a table (`OutboxDelivery`) and a fan-out relay; an unconsumed
  delivery is a new thing to monitor (also a new thing that *can* be monitored).
- **−** Presentation strings still ride the bus for notification events until the
  deferred Core-boundary move (Fork B) lands; this ADR narrows the smell to one
  event family rather than removing it.

## Alternatives considered

- **`send_robust` instead of per-consumer delivery rows.** Rejected — it stops one
  consumer's exception from propagating, but leaves all consumers in one shared
  transaction with one shared retry/dead-letter fate. It does not give independent
  retry, and a consumer doing synchronous financial work in the shared transaction
  is still unsafe.
- **Build the full delivery table now (skip staging).** Rejected — with exactly one
  enqueue-only consumer today (`receivers.py`), per-consumer delivery rows have no
  second fate to protect. Building them before the financial consumer is the
  speculative boundary the codebase's strangler discipline (ADR-0014) avoids.
- **Strip presentation off the bus now (the fuller "facts + policy layer" move).**
  Rejected *for this ADR* — it forces a notification-policy layer and a ~30-call-
  site rewrite that belong to the Core-boundary re-derivation, and would stall the
  settlement unblock. Kept reachable, deliberately deferred.
- **Emit-time dedup collapse (partial-unique on PENDING).** Rejected — racy (a
  PROCESSED first row no longer blocks a second witness) and redundant once
  consumer-side dedup on `dedup_key` is mandatory. Consumer-side dedup, delegated to
  `post_journal`, is the contract.
- **A dedicated money-dedup table in the outbox.** Rejected — `post_journal`'s
  `idempotency_key` (ADR-0004) is already the exactly-once guarantee; duplicating it
  in the outbox creates a second source of truth for "applied," the anti-pattern
  ADR-0002 exists to prevent.
- **Keep the notification-shaped bus and give money a separate, parallel path.**
  Rejected — two durable-eventing mechanisms to maintain, and settlement would not
  share the replay/dead-letter/monitoring the outbox already provides. One event
  log, two lanes, is fewer moving parts than two logs.
