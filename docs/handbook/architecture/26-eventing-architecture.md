# Architecture / 26 — Eventing Architecture

> How Wepl announces that something happened, durably. Domain events are how
> modules stay decoupled and how effects (notifications, feeds, webhooks) fan out
> — and in a financial system, **an event must never be lost and must never lie**.
> The transactional outbox is how both are guaranteed.

Grounded in [ADR-0006](../../adr/0006-transactional-outbox.md); realised in
`apps/core` (`events.py`, `tasks.py`).

---

## The problem eventing solves

Modules must react to each other's facts — a contribution is paid, so notify the
member and update the feed — without calling into each other directly (which would
re-couple them, violating [Module Boundaries Rule 4](22-module-boundaries.md)). The
naive solution, "publish to a message broker after saving," has a fatal flaw for
money: the save and the publish are *two* operations, and a crash between them
either **loses the event** (saved, never published) or **lies** (published, then the
save rolled back). Neither is acceptable when the event is "money moved."

## The solution — the transactional outbox

> `emit(...)` writes an **`OutboxEvent` row in the current database transaction.**

Because the event is written in the *same* transaction as the business change:

- If the transaction **rolls back**, the event vanishes with it — no lie. A
  rolled-back payment cannot emit "payment succeeded" (**P-9**).
- If the process **crashes** after commit, the event is *already durably in
  Postgres* — no loss. It will be delivered when the relay next runs.

The event's fate is bound to the business fact's fate. This is the eventing analogue
of the ledger's "one atomic transaction" property, and it is not optional for a
financial platform.

## The delivery relay

The **`process_outbox`** relay (`apps/core/tasks.py`, a Celery task) reads
undelivered `OutboxEvent` rows and delivers them by **re-firing the `domain_event`
signal**. Delivery is **at-least-once**: the relay may deliver an event more than
once (after a crash mid-delivery, on retry), and that is *fine by design* because
consumers are idempotent (below). We choose at-least-once over exactly-once
deliberately — exactly-once across a process boundary is a myth, and building for
at-least-once with idempotent consumers is the honest, robust choice.

```
  business txn ──┬── domain change (e.g. post_journal)
                 └── emit() → OutboxEvent row     [same transaction, commits together]
                                  │
                    process_outbox (Celery)  ── re-fire domain_event signal ──►
                                  │                          consumers
                                  │                    (notifications, activity,
                                  ▼                     webhooks-out, …)
                        mark delivered            each dedupes on event_id
```

## Consumers dedupe idempotently

Consumers register receivers in their `AppConfig.ready()` and **dedupe on
`Notification.event_id`** (and equivalent per-consumer keys). Because delivery is
at-least-once, a consumer *will* occasionally see the same event twice; deduping on
the event id makes the second delivery a no-op. A member is never double-notified;
a feed never double-posts. Idempotency at the consumer is the price of durability at
the relay, and it is a price worth paying.

## The `emit()` contract (fixed and narrow)

`emit()`'s signature is fixed across ~30 call sites, and its payloads are
**JSON-serialisable primitives** — IDs, strings, numbers — **never ORM objects**.
Two reasons, both structural:

1. **Serialisability** — an event may be delivered long after the objects it
   references have changed; carrying primitive IDs (which the consumer re-reads)
   keeps the event a stable fact, not a stale object graph.
2. **Boundary hygiene** — an event must not smuggle a module's internal ORM model
   across a boundary ([Module Boundaries Rule 4](22-module-boundaries.md)). Passing
   IDs keeps modules decoupled; passing objects would re-couple them.

The narrowness of the contract is deliberate: an event bus is only as durable as its
least-serialisable payload.

## What events are for (and not for)

**Events are for effects, not truth.** The book of record is the ledger; events
*announce* changes to it so that downstream effects can happen. Critically:

- **No balance is derived from an event.** Balances derive from journal lines,
  synchronously, in the posting transaction (**P-3**). An event that was delayed or
  redelivered cannot affect a balance.
- **Events drive delivery** — notifications ([ADR-0015](../../adr/0015-multi-channel-notification-delivery.md)),
  activity feeds ([ADR-0016](../../adr/0016-activity-feed-architecture.md)),
  reminders, search indexing ([ADR-0017](../../adr/0017-search-architecture.md)),
  and (Phase 7) external webhooks.
- **Events are lag-tolerant.** Correctness never depends on *when* an event is
  delivered, only that it *eventually* is, at-least-once.

This division — truth synchronous and local, effects asynchronous and event-driven —
is the same dividing line drawn in [System Architecture](20-system-architecture.md),
seen from the eventing side.

## Webhooks-out are just external consumers (Phase 7)

The BaaS webhook system is not new infrastructure — it is **another consumer of the
outbox**. External webhooks-out will be delivered by the same at-least-once relay,
signed, retried, and deduplicated by the receiver on the event id. This is why the
[Business Model](../product/04-business-model.md) can treat BaaS as a near-term
extension rather than a rebuild: the durable-eventing work done in Phase 2 *is* the
webhook engine. Building the outbox correctly once pays off three times
(notifications, feeds, external webhooks).

## Failure behaviour

| Failure | Outcome |
|---------|---------|
| Business txn rolls back | Event discarded with it — no phantom event |
| Crash after commit, before delivery | Event durable in Postgres; delivered on next relay run |
| Crash mid-delivery | Redelivered; consumers dedupe — no double effect |
| Redis/broker down | Relay pauses; events accumulate durably; drain when broker returns |
| A consumer throws | That delivery retries; the event is not lost |

There is no failure mode in this table that loses an event or fabricates one. That
is the property the outbox exists to provide.

## What eventing must never become

- **Never the source of a balance or any money truth** (**P-1/P-3**).
- **Never a synchronous cross-module call dressed up as an event** — if module A
  *needs* B's response before committing, that is a service call within the
  transaction, not an event.
- **Never a carrier of ORM objects or non-serialisable payloads.**
- **Never assumed exactly-once** — every consumer is written to tolerate redelivery.

---

*Continue to [Payments Architecture](27-payments-architecture.md).*
