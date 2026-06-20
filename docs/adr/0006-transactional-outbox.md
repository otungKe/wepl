# ADR-0006: Transactional outbox for durable domain events

- **Status:** Proposed
- **Date:** 2026-06-19
- **Phase:** 2

## Context
`apps/core/events.py` emits events via `transaction.on_commit` + in-process Django
signals. If the process dies between COMMIT and dispatch, the event is lost. This is
tolerable for notifications but unsafe once events drive money, settlement, or
external webhooks (Phase 7).

## Decision
Adopt the transactional outbox pattern: `emit()` writes an `OutboxEvent` row inside
the same DB transaction as the state change. A relay worker delivers events
at-least-once to idempotent consumers, with retry/backoff and a dead-letter state.
`emit()`'s public signature is preserved so callers don't change.

## Consequences
- **+** No lost events; replayable; foundation for outbound webhooks.
- **+** Decouples producers from consumer availability.
- **−** Requires a relay process and idempotent consumers (dedupe by event id).
- **−** At-least-once delivery semantics (consumers must be idempotent).

## Alternatives considered
- *Direct broker publish in `on_commit`:* rejected — still loses events on crash
  between commit and publish; no durable record.

## Implementation notes (design review 2026-06-20)
Grounded against the current `apps/core/events.py`:
- **Loss window** is COMMIT → `on_commit` → signal → `.delay()` enqueue. Once in
  Redis, Celery `acks_late` covers it. The outbox closes the pre-enqueue gap,
  including a **broker outage at `emit()` time** (today `.delay()` raises inside
  `on_commit` after the 200 response → silent drop).
- **`emit()` today is notification-specific** (payload = `user_id/title/message` +
  FK hints), not a general domain event. Scope = make notification delivery durable
  while keeping the signature; store `payload` as **generic JSON** so Phase 7
  webhooks reuse the table.
- **`emit()` becomes a synchronous `OutboxEvent.objects.create(...)`** (no
  `on_commit`) — atomic with the state change in an `atomic` block; rollback still
  discards the event (no phantoms).
- **Idempotency requires a new key:** `Notification` has none — add a unique
  `event_id` so at-least-once redelivery is a no-op.
- **Relay** claims with `select_for_update(skip_locked=True)`; schedule at a
  **seconds interval** (Celery `crontab` is minute-granularity). Reuse the P0-08
  reconcile/alert pattern for lag + dead-letter alerts.
- **Open decision:** relay re-fires the `domain_event` signal (keeps pluggable
  fan-out — recommended) vs. directly creating notifications.

**Status: not yet implemented** — design only.
