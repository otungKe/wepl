# Phase 2 — Durable Eventing (Transactional Outbox)

**Status:** 🔴 Not started · **Depends on:** Phase 0 · **ADR:** [0006](../adr/0006-transactional-outbox.md)

## Problem
`apps/core/events.py` dispatches domain events via `transaction.on_commit` +
in-process Django signals. If the process dies between COMMIT and signal dispatch,
**the event is lost**. Acceptable for notifications today; unacceptable once events
drive money, settlement, or external webhooks.

## Objective
A transactional **outbox**: events are written to an `outbox` table inside the same
DB transaction as the state change, then a relay delivers them at-least-once to
consumers (notifications now; webhooks-out and analytics later).

## Work items
- **P2-01** `OutboxEvent` model (id, type, payload JSON, status, attempts,
  created/processed_at) written in-transaction by `emit()`.
- **P2-02** Relay worker (Celery beat + worker) that polls unprocessed events and
  dispatches with retry/backoff and a dead-letter state.
- **P2-03** Idempotent consumers (dedupe by event id) — notifications first.
- **P2-04** Backward-compatible `emit()` signature so callers don't change.
- **P2-05** Observability: outbox lag, dead-letter alerts.

## Acceptance criteria
- Killing the relay then restarting delivers all pending events exactly-effectively-once.
- A consumer exception moves the event to dead-letter, not silent loss.

## Exit criteria
- [ ] `emit()` is durable; no event path relies solely on in-process signals.
- [ ] Relay metrics + dead-letter alerting in place.
