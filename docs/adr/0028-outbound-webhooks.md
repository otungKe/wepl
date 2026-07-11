# ADR-0028: Outbound webhooks on the transactional outbox

- **Status:** Proposed
- **Date:** 2026-07-11
- **Deciders:** Architecture review
- **Phase:** 7 (Banking-as-a-Service) · work item P7-03
- **Depends on:** [ADR-0006](0006-transactional-outbox.md) (outbox), [ADR-0027](0027-baas-api-key-authentication.md) (tenants/keys)

## Context
BaaS integrators need to be told when things happen on their tenant's ledger — a
collection settled, a payout completed, a KYC decision made — without polling. That
means **outbound webhooks**. In a money platform a webhook must never be lost and must
never lie (announce a movement that rolled back), exactly the guarantee the internal
domain-event system already provides.

Wepl already has a durable, at-least-once event backbone: `emit()` writes an
`OutboxEvent` in the business transaction and `process_outbox` delivers it to
consumers that dedupe idempotently ([Eventing Architecture](../handbook/architecture/26-eventing-architecture.md),
[ADR-0006](0006-transactional-outbox.md)). Outbound webhooks should be **another
consumer of that outbox**, not a parallel mechanism — building a second event path
would risk the very loss/lie problems the outbox was created to eliminate.

## Decision
1. **Webhooks are outbox consumers.** External delivery is driven by the same
   `OutboxEvent` stream that drives notifications and feeds. No new event source; the
   Phase 2 investment *is* the webhook engine.
2. **Per-tenant subscriptions:** a tenant registers endpoint URL(s) and the event types
   it wants; delivery is scoped to that tenant's own events ([ADR-0027](0027-baas-api-key-authentication.md))
   — a tenant can never receive another tenant's events (risk R11).
3. **Signed payloads:** every delivery carries an HMAC signature over the body using a
   per-endpoint secret, plus a timestamp, so the receiver can verify authenticity and
   reject replays. Payloads are JSON primitives (IDs/strings/numbers), never internal
   ORM shapes (mirrors the `emit()` contract).
4. **At-least-once with retries + backoff + dead-letter:** transient delivery failures
   retry with exponential backoff; exhausted deliveries dead-letter and alert. Each
   delivery carries a stable event id so **receivers dedupe** — we require idempotent
   receivers, exactly as internal consumers are (P-9). We do not attempt exactly-once.
5. **Observable:** delivery lag, retry depth, and dead-letter counts are surfaced
   ([ADR-0020](0020-observability-standard.md)), and a tenant can inspect/replay recent
   deliveries.
6. **No money truth in the webhook.** A webhook *announces* a ledger fact; the
   integrator confirms state via the API (which reads the projection). A delayed or
   redelivered webhook can never affect a balance (P-3).

## Consequences
- **+** Webhooks inherit the outbox's durability and honesty for free: no lost events,
  no phantom events, tenant-scoped, signed.
- **+** One event backbone serves internal notifications, feeds, *and* external
  webhooks — built once, used three times.
- **−** Adds egress concerns: endpoint validation, SSRF protection, secret management,
  and per-tenant delivery isolation so one slow endpoint can't starve others.
- **−** Requires a delivery-inspection/replay surface for integrators.

## Alternatives considered
- **A separate webhook queue independent of the outbox:** rejected — a second event
  path re-introduces the loss/lie risk the outbox eliminates, and doubles the
  machinery.
- **Exactly-once delivery:** rejected — impossible across a network boundary; we choose
  honest at-least-once + required receiver idempotency.
- **Polling instead of webhooks:** rejected as the primary mechanism — wasteful and
  high-latency; a read API exists for reconciliation, but push is the product.
