# ADR-0015: Multi-channel notification delivery & dead-letter

- **Status:** Accepted (channel strategy + dead-letter implemented; templates/digests deferred)
- **Date:** 2026-06-23
- **Relates to:** Platform Hardening Review §2.7 + Action Plan P1 #10.

## Context

Notifications had the right spine — outbox-driven, idempotent via
`Notification.event_id` — but **delivery was hardcoded** in the Celery task: create
the in-app row, then fire FCM. Adding a channel meant editing the task, there was
**no per-channel routing**, and a push that exhausted its retries was **silently
lost** (no dead-letter).

## Decision

### Channel strategy + preference routing
- **`apps/notifications/channels.py`**: a `NotificationChannel` port with concrete
  `InAppChannel` (durable inbox row, idempotent on `event_id`) and `PushChannel`
  (FCM, dispatched async). A `CHANNELS` registry; new surfaces (email/SMS/WhatsApp)
  register a class — no task edits.
- **`channels_for(notification_type, prefs)`** is the single routing matrix: it
  returns the ordered channel keys for a notification given the user's preferences
  (empty = suppressed). It preserves today's semantics (`push_enabled` master switch
  + per-category opt-out) so behaviour is unchanged.
- **`send_notification`** now resolves channels from the matrix and delivers through
  them. The in-app row is treated as the durable record (retried, idempotent); other
  channels are best-effort.

### Dead-letter
- **`NotificationDeadLetter`** captures a delivery that failed on a channel after
  retries (user, type, channel, payload, error, `resolved_at`), with a read-only
  admin. The in-app channel dead-letters once `send_notification` exhausts retries;
  the push task dead-letters when its own retries are exhausted instead of dropping.
  Recording is best-effort (`deadletter.record`) and never breaks delivery.

## Consequences

- **+** Adding a channel is "implement + register," not a task rewrite.
- **+** Failed deliveries are queryable/replayable, not lost — real reliability.
- **+** Routing is one auditable function instead of inline `if` branches.
- **−** No automatic replay worker yet (rows are recorded; replay is manual/ops).

## Deferred (documented, not built)

- **Per-channel preference fields** (`email_enabled`, `sms_enabled`) + decoupling the
  in-app inbox from the push master switch — needs a prefs migration + product
  sign-off, so routing keeps today's master-switch semantics for now.
- **Concrete email/SMS/WhatsApp channels** (the seam is ready; an SMS gateway already
  exists in `users.sms`).
- **Templates + i18n** (messages are still string-built at the call site).
- **Digests / quiet-hours / aggregation**, and a **dead-letter replay** task.

## Alternatives considered

- **Keep hardcoded delivery, just add a try/except for the lost push.** Rejected —
  fixes the symptom, not the "adding a channel edits the task" coupling the review
  flagged.
- **A full pub/sub fan-out service now.** Deferred — the outbox already provides
  durable fan-out; this ADR is the delivery-layer slice.
