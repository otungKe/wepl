# Phase 2 — Durable Eventing (Transactional Outbox)

**Status:** 🟢 Done (2026-06-20) · **Depends on:** Phase 0 · **ADR:** [0006](../adr/0006-transactional-outbox.md)

## Problem (confirmed against the code)
`apps/core/events.py` `emit()` registers a `transaction.on_commit` callback that
fires an in-process Django `Signal` (`domain_event`); the notifications app's
receiver then calls `send_notification.delay(...)` (enqueue to Celery/Redis).

The event is durable only *once it reaches Redis* (Celery `acks_late` covers worker
crashes from there). The **loss window is COMMIT → on_commit → signal → `.delay()`
enqueue**, with two real failure modes:
1. **Process dies** right after commit, before/within the `on_commit` callback → lost.
2. **Broker down at dispatch time** → `.delay()` raises *inside* `on_commit`; the
   request already returned 200 → notification silently dropped.

Acceptable for notifications today; unacceptable once events drive money,
settlement, or external webhooks (Phase 7).

## Scope note (what these "events" actually are)
Today `emit()` is **notification-specific** — its payload is hardcoded notification
fields (`user_id`, `title`, `message`, + FK deep-link hints), and the only consumer
is notifications. So Phase 2 = *make notification delivery durable*, **not** a
general domain-event redesign. The `OutboxEvent.payload` is nonetheless stored as
**generic JSON** so Phase 7 (outbound webhooks) and any future real domain events
reuse the same table + relay.

## Priority calibration
This is **reliability/UX** (don't silently drop notifications), **not** money-safety
— ledger correctness (Phase 0) does not depend on this bus. Its strategic value is
being the **durable substrate for Phase 7 webhooks**. Self-contained and low-risk,
so it can be scheduled flexibly.

## Objective
A transactional **outbox**: events are written to an `outbox` table inside the same
DB transaction as the state change, then a relay delivers them at-least-once to
idempotent consumers (notifications now; webhooks-out and analytics later).

## Work items
- **P2-01 — `OutboxEvent` model.** Fields: `id`, `event_type`, `payload` (JSONField,
  generic), `status` (`PENDING`/`PROCESSED`/`DEAD`), `attempts`, `created_at`,
  `processed_at`, `last_error`. Index on `(status, created_at)` for the relay claim.
- **P2-02 — `emit()` becomes a synchronous insert.** Drop `on_commit`; `emit()` does
  `OutboxEvent.objects.create(event_type=…, payload={…})` — inside the caller's
  transaction when in an `atomic` block (atomic with the state change), or its own
  commit otherwise. Preserves existing rollback-safety (a rolled-back txn discards
  the event row) **and** closes the crash gap.
- **P2-03 — Relay.** A scheduled task claims `PENDING` rows with
  `select_for_update(skip_locked=True)` (safe across workers), dispatches each, marks
  `PROCESSED`; on failure increments `attempts` + records `last_error` with backoff,
  moving to `DEAD` after N attempts. **Scheduling:** Celery beat `crontab` is
  minute-granularity — use a **seconds interval** (`'schedule': 10.0`) or a
  self-rescheduling task for timely notifications.
- **P2-04 — Keep the consumer fan-out.** The relay re-fires `domain_event` (or calls
  a registered-handler list) rather than hardcoding notifications, preserving the
  "add a consumer without touching producers" design. Net path:
  relay (durable) → signal → `send_notification.delay`.
- **P2-05 — Idempotent consumers.** `Notification` has **no dedupe key today** —
  add a unique nullable `event_id` (the `OutboxEvent` PK) so at-least-once
  redelivery is a no-op `get_or_create`. (Without this, a relay crash after dispatch
  but before marking `PROCESSED` creates duplicate notifications.)
- **P2-06 — Observability.** Outbox lag (age of oldest `PENDING`), `DEAD` count;
  log + Sentry alert (reuse the P0-08 reconcile/alert pattern).
- **P2-04 (compat)** `emit()`'s public signature is unchanged → ~30 call sites
  (`_notify`/`_emit_event`) untouched.

## Open decision (for the owner)
**Relay dispatch style:** re-fire the in-process `domain_event` signal (keeps the
pluggable multi-consumer fan-out — *recommended*, and required for Phase 7 webhooks)
vs. the relay directly creating notifications (simpler, but re-couples the relay to
the notifications app).

## Acceptance criteria
- Killing the relay then restarting delivers all pending events
  exactly-effectively-once (no loss, no duplicate `Notification`).
- A consumer exception moves the event to `DEAD`, never silent loss.
- A broker outage at `emit()` time does **not** drop the event (it is persisted and
  delivered when the relay next runs).

## Test plan
1. `emit()` inside `atomic` writes a `PENDING` `OutboxEvent`; a rolled-back txn writes none.
2. Relay delivers a `PENDING` event and marks it `PROCESSED`.
3. Re-running the relay over an already-delivered event creates no duplicate (idempotent).
4. A consumer that raises → event lands in `DEAD` after N attempts with `last_error`.

## Exit criteria — ✅ ALL MET (2026-06-20)
- [x] `emit()` is durable (persisted in-transaction via `OutboxEvent`); no event path
      relies on in-process signals/`on_commit` (`apps/core/events.py`).
- [x] Relay (`apps/core/tasks.process_outbox`, beat every 10s) with
      `select_for_update(skip_locked=True)` claim, attempt-based backoff, and `DEAD`
      dead-lettering + Sentry alert.
- [x] Consumers idempotent — `Notification.event_id` unique; `NotificationService`
      / `send_notification` dedupe via `get_or_create(event_id=…)`.
- [x] Dead-letter alerting in place (lag metric is a follow-up; `DEAD` count alerts).

## Implementation (2026-06-20)
- `apps/core/models.py` — `OutboxEvent` (event_type, payload JSON, status, attempts,
  last_error, timestamps; `(status, created_at)` index).
- `apps/core/events.py` — `emit()` writes an `OutboxEvent` in the current
  transaction (signature unchanged → ~30 call sites untouched).
- `apps/core/tasks.py` — `process_outbox` relay (re-fires `domain_event`, threading
  `outbox_event_id` for consumer dedupe).
- `apps/notifications/` — `Notification.event_id` unique + dedupe through
  `receivers` → `send_notification` → `NotificationService.create`.
- Chosen dispatch style: **relay re-fires the signal** (keeps pluggable fan-out; the
  substrate for Phase 7 webhooks).
- Tests: `apps/core/tests_outbox.py` (durable write, rollback-safety, delivery,
  idempotent redelivery, dead-lettering). Suite green (139).
- **Follow-up (non-blocking):** outbox *lag* gauge (oldest PENDING age) + a
  `PROCESSING` claim phase if dispatch I/O under the row lock becomes a concern at
  higher volume.
