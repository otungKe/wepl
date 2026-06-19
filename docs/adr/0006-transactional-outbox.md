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
