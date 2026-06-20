# Phase 2 — Durable Eventing (Transactional Outbox)

**Status:** 🟢 Done (P2-01 → P2-05) · **Depends on:** Phase 0 · **ADR:** [0006](../adr/0006-transactional-outbox.md)

## Problem (confirmed against the code)
`apps/core/events.py` `emit()` registered a `transaction.on_commit` callback that
fired an in-process Django `Signal` (`domain_event`); the notifications app's
receiver then called `send_notification.delay(...)` (enqueue to Celery/Redis).

The event was durable only *once it reached Redis*. The **loss window was COMMIT →
on_commit → signal → `.delay()` enqueue**, with two real failure modes:
1. **Process dies** right after commit, before/within the `on_commit` callback → lost.
2. **Broker down at dispatch time** → `.delay()` raises *inside* `on_commit`; the
   request already returned 200 → notification silently dropped.

Acceptable for notifications; unacceptable once events drive money, settlement, or
external webhooks (Phase 7).

## Scope note
Today `emit()` is **notification-specific** — its payload is hardcoded notification
fields (`user_id`, `title`, `message`, + FK deep-link hints), and the only consumer
is notifications. So Phase 2 = *make notification delivery durable*, **not** a
general domain-event redesign. The `OutboxEvent.payload` is stored as **generic
JSON** so Phase 7 (outbound webhooks) and future domain events reuse the same table
and relay.

## Objective
A transactional **outbox**: events are written to an `outbox` table inside the same
DB transaction as the state change, then a relay delivers them at-least-once to
idempotent consumers (notifications now; webhooks-out and analytics later).

## Work items
- [x] **P2-01** `OutboxEvent` model (`apps/core/models.py`) — `event_type`, `payload`
  (generic JSON), `status` (`PENDING`/`PROCESSED`/`DEAD`), `attempts`, `last_error`,
  timestamps; `(status, created_at)` index. Written in-transaction by `emit()`.
  Migration: `apps/core/migrations/0001_initial.py`.
- [x] **P2-02** `emit()` becomes a synchronous in-transaction insert — drops
  `on_commit`; rollback-safety preserved. `process_outbox` relay claims `PENDING`
  rows with `select_for_update(skip_locked=True)` (safe across workers), re-fires
  `domain_event` signal (keeps pluggable fan-out for Phase 7 webhooks), marks
  `PROCESSED`; backoff → `DEAD` after N attempts. Beat schedule: every 10 s.
- [x] **P2-03** Idempotent notification consumer — `Notification.event_id` (unique
  BigInt, the `OutboxEvent` PK); `NotificationService.create` dedupes via
  `get_or_create(event_id=…)`, threaded through `receivers → send_notification`.
  Migration: `apps/notifications/migrations/0012_notification_event_id.py`.
- [x] **P2-04** `emit()` signature unchanged — ~30 call sites untouched.
- [x] **P2-05** Observability — Sentry `capture_message` on dead-letter events;
  dead count logged on every relay run. Outbox lag gauge is a follow-up.

## Acceptance criteria
- Killing the relay then restarting delivers all pending events exactly-effectively-once. ✅
- A consumer exception moves the event to `DEAD`, never silent loss. ✅
- A broker outage at `emit()` time does not drop the event. ✅

## Exit criteria — ALL MET (2026-06-20)
- [x] `emit()` is durable (persisted in-transaction via `OutboxEvent`); no event path
      relies on in-process signals/`on_commit`.
- [x] Relay with `select_for_update(skip_locked=True)` claim, retry/backoff, `DEAD`
      dead-lettering + Sentry alert.
- [x] Consumers idempotent — `Notification.event_id` unique; dedupe via `get_or_create`.
- [x] Dead-letter alerting in place (lag metric is a follow-up).

## Tests (`apps/core/tests_outbox.py`)
- Durable in-transaction write; rollback-safety (no phantom events).
- Relay delivery → `PROCESSED`; idempotent redelivery creates no duplicate notification.
- Dead-lettering after max attempts with `last_error` recorded.
- Suite green (139 tests).
