# Phase 2 — Durable Eventing (Transactional Outbox)

**Status:** 🟢 Done (P2-01 → P2-05) · **Depends on:** Phase 0 · **ADR:** [0006](../adr/0006-transactional-outbox.md)

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
- [x] **P2-01** `OutboxEvent` model (`apps/core/models.py`) — UUID pk, event_type,
  payload JSON, status (pending/processing/delivered/dead_letter), attempts,
  created/processed_at, error. Written in-transaction by `emit()`.
  Migration: `apps/core/migrations/0001_outbox_event.py`.
- [x] **P2-02** Relay worker — `deliver_outbox_event` Celery task (fast-path,
  scheduled on_commit) + `relay_outbox_events` beat task (every minute, safety net
  for events older than 30 s). Both in `apps/core/tasks.py`.
  Beat schedule entry added to `config/settings/base.py`.
- [x] **P2-03** Idempotent notification consumer — `send_notification` task
  accepts `outbox_event_id`; skips if a `Notification` with that `source_event_id`
  already exists. `Notification.source_event_id` field added
  (migration `apps/notifications/migrations/0012_notification_source_event_id.py`).
- [x] **P2-04** `emit()` signature unchanged — same positional/keyword args as
  before; callers require no changes.
- [x] **P2-05** Observability — `OutboxEventAdmin` with requeue action;
  dead-letter count logged as WARNING by relay on every run.

## Acceptance criteria
- Killing the relay then restarting delivers all pending events exactly-effectively-once. ✅
- A consumer exception moves the event to dead-letter, not silent loss. ✅

## Exit criteria
- [x] `emit()` is durable; no event path relies solely on in-process signals.
- [x] Relay metrics + dead-letter alerting in place.
