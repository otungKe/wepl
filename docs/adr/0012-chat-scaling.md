# ADR-0012: Chat data model & real-time scaling

- **Status:** Accepted (read high-water-mark, cheap unread, keyset pagination done; presence/backpressure deferred)
- **Date:** 2026-06-23
- **Relates to:** Platform Hardening Review §2.4 + finding #2 + Action Plan P2 #11.

## Context

Chat worked but had scalability ceilings (review §2.4). Two of the listed items
were already addressed earlier this cycle:
- **Reactions** are a relational `MessageReaction` table with a uniqueness
  constraint — not the unqueryable JSON the review warned about.
- **Channel groups are tenant-scoped** (`group_for_conversation_id`, ADR-0008
  follow-up / PR #33).

Three ceilings remained: unbounded message fetch, an N+1 unread count, and
timestamp-based read tracking.

## Decision

### Read high-water-mark + O(1) unread
- `ConversationReadStatus` gains **`last_read_message_id`** (the high-water-mark).
  `mark_read` advances it to the conversation's latest message id.
- `get_unread_summary` is rewritten from a per-conversation Python `COUNT` loop
  (N+1) into **one aggregate query**: each message is compared to its
  conversation's read high-water-mark via a correlated subquery, then grouped by
  community. A data migration backfills `last_read_message_id` from the existing
  `last_read_at` so counts stay correct across the switch.

### Keyset message pagination
- `GET /conversations/<id>/messages/` is now **keyset-paginated on id**: `?limit=`
  (default 50, max 200) returns the most recent page ascending; `?before=<id>`
  scrolls older. No `OFFSET` (stable under concurrent inserts). The response shape
  is unchanged (a JSON list).

## Consequences

- **+** Unread is a single indexed query regardless of conversation/message count.
- **+** Message fetch is bounded — removes an unbounded-result memory/DoS risk and
  gives clients a stable scroll-back cursor.
- **− Behaviour change:** the messages endpoint now returns at most 50 messages by
  default (was: all). The **shape is unchanged** (still a list), and chat UIs render
  recent-first with scroll-back, so this matches the expected contract — but the
  mobile client should adopt `before=` for history. Flagged for the client team.

## Deferred (the rest of §2.4)

- **Presence**, **per-socket rate limit / backpressure**, and a **resume-from-cursor
  reconnect** protocol on the WebSocket.
- **Write-fanout** for very large communities (read-fanout is fine at current scale;
  the message create already emits via the outbox).
- **Message search** (covered by the Search ADR).

## Alternatives considered

- **DRF `CursorPagination` on the endpoint.** Rejected for now: it changes the
  response shape to `{results,next,previous}` (breaking the mobile client). The
  id-keyset `limit`/`before` keeps the list shape while still being O(1) and
  OFFSET-free; a versioned cutover to the envelope can follow under `/api/v2`.
- **Maintained per-(user,conversation) unread counters.** Heavier write path; the
  high-water-mark + single aggregate is exact and cheap enough at current scale.
