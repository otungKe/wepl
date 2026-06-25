# ADR-0016: Activity feed — typed events, visibility & fan-out model

- **Status:** Accepted (typed events + visibility + cursor pagination implemented; cross-user social feed deferred)
- **Date:** 2026-06-25
- **Relates to:** Platform Hardening Review §2.8 + Action Plan P2 #14.

## Context

The activity feed was the thinnest social surface in the platform (review score
3.5/10). The `Activity` model stored a single pre-rendered `message` string per
row, written by `ActivityService.log_activity(user, activity_type, message)` from
~7 call sites. The review flagged three structural problems:

1. **Pre-rendered strings.** A stored sentence (`"Alice contributed KES 500 to
   Chama Pool"`) cannot be re-rendered, localized, or reworded retroactively, and
   the actor's name is frozen at write time. The view even string-replaced the
   actor's name back to "You" at read time — a symptom of the wrong storage shape.
2. **No visibility rules.** Rows carried no audience. The feed worked only because
   the view hard-filtered to `user=request.user`; the moment a community or social
   feed is added, there is no field that says *who may see this*, which is a
   privacy-leak class of bug.
3. **No fan-out decision and offset pagination.** Reads used `LIMIT/OFFSET`, which
   shifts results as rows are inserted (the feed is append-heavy), and there was no
   stated position on read- vs write-fan-out at scale.

## Decision

### Typed events: store params, render at read time
`Activity` gains a `params` (JSON) column. Writers pass structured primitives
(`{"community_name": "Chama", "amount": "500"}`) and a `verb` (the existing
`activity_type`); the human sentence is produced by a small renderer registry
(`apps/activity/render.py`) at **read** time, keyed by verb. The denormalized
`message` column is retained as a render cache and back-compat fallback (old rows
and unknown verbs still render). This makes wording/localization a read-time
concern and keeps the actor's identity live.

### Visibility is a first-class field
`Activity` gains `visibility` (`private` | `community` | `public`, default
`private`) and a nullable `community` FK for scoping. A queryset helper
`Activity.objects.visible_to(user)` encodes the rule **once**: a row is visible if
the user is its actor, or it is `community`-scoped and the user is an active member
of that community, or it is `public`. The personal feed and any future community
feed both go through this helper — visibility can never be re-implemented per
endpoint. Community lifecycle events are now written `community`-scoped so the
feature is exercised and tested, not theoretical.

### Read-fan-out (store once)
We commit to **read-fan-out**: one row per event, rendered and audience-filtered
at read time — no per-recipient copies. Writes stay O(1); reads are bounded by
indexes (`(user, -created_at)` for personal, `(community, -created_at)` for
community feeds) and keyset pagination. Write-fan-out (materialized per-recipient
feeds) is the v2 lever if a high-cardinality public feed is ever built; the typed
event + visibility shape is exactly what a fan-out worker would consume.

### Cursor pagination
The feed endpoint uses keyset cursor pagination (`ActivityCursorPagination`,
ordering `-created_at, -id`) instead of offset — stable under concurrent inserts
and no total-count leak, consistent with the financial lists (ADR-0021).

### Back-compatible service surface
`ActivityService.record(actor, verb, *, params, message, visibility, community)`
is the new typed door; `log_activity(user, activity_type, message)` is kept as a
thin shim so no caller breaks. Existing call sites were migrated to pass `params`
and (for community events) `visibility`/`community`.

## Consequences

- **Positive:** wording/localization is now a read concern; visibility is enforced
  in one place; the feed is insert-stable; the model is ready for a community or
  social feed without a migration of intent. The activity app now has a real test
  suite (it had a 3-line stub).
- **Negative / deferred:** no cross-user *social* feed endpoint ships here (only the
  personal feed plus the visibility-correct query helper); no aggregation
  ("3 people joined") or write-fan-out; localization catalogue is not built (the
  renderer is English-only for now, but render-at-read makes it a drop-in later).
- **Neutral:** `message` is intentionally not dropped — it is the fallback for old
  rows and unknown verbs, and a cheap search target.
