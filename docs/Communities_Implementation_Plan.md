# Communities — Implementation Plan

Prioritised remediation roadmap from the audit set (Domain, Business Rules,
Backend, Integration, RBAC, Production Readiness). Grouped by severity; each item
names its fix location and the platform pattern to reuse. No new product features
— every item closes a gap the audit identified.

---

## CRITICAL — before real money at real scale

**CR-1 · Make deletion safe (D-1 / G-12)**
- Switch `Contribution.community`, `WelfareFund.community`, `SharesFund.community`
  to `on_delete=PROTECT`.
- `CommunityService.delete_community` (new — move logic out of the view): refuse
  when any linked fund/contribution has posted movements or non-zero ledger
  context; allow hard delete only for never-funded shells; otherwise instruct
  archive.
- Tests: delete-with-posted-funds refused; shell delete still works.

**CR-2 · Community lifecycle (D-2 / G-7 / G-8)**
- `Community.status`: `active / suspended / archived` (+ index), default active.
- Single chokepoint check (`require_active_community(community)`) called at:
  join/request paths, contribution & fund creation, welfare claim / advance /
  disbursement initiation, conversation creation. Reads stay allowed (members can
  see history of an archived community).
- Transitions service-owned + audited + evented: owner may archive; only ops may
  suspend/unsuspend (Back Office action via `communities.manage`, with
  `record_action`).
- Discover/search exclude non-active. Reminders skip non-active communities.

## HIGH — correctness and governance defects

**H-1 · Cooling-off clock on rejoin (G-4)**
Add `rejoined_at` (or reset `joined_at`) on reactivation in `join_community`;
`check_cooling_off` uses the later timestamp. Regression test: leave→rejoin→claim
blocked.

**H-2 · Owner departure rule (G-1)**
In `leave_community`: if leaver is `created_by`, refuse with "transfer ownership
first" (mirror last-admin guard). Also handle in account-deletion flow (G-2):
enumerate owned communities, require transfer/closure, ops escalation for
orphans (transfer escape hatch already exists).

**H-3 · Enforce `invite_permission` + rotation (G-5)**
- `get_invite_code` honours the setting (creator/admins/members) via
  `community_role`.
- `POST /<id>/invite/rotate/` — admin rank, audited, regenerates the code.
- Tests for all three settings + rotation invalidating the old code.

**H-4 · Ban semantics (G-3)**
Replace membership `is_active` semantics with `status`:
`active / left / removed / banned` (data migration: active→active, inactive→left;
removal paths set `removed`). `request_to_join` refuses `banned`; review screen
payload includes prior `removed/banned` state. Owner/creator may ban on removal.

**H-5 · Community domain events on the outbox (Backend §2)**
Emit via `emit()`: `community_created`, `member_joined`, `member_left`,
`member_removed`, `role_changed`, `ownership_transferred`,
`community_settings_changed`, `community_archived/suspended`,
`join_request_created/approved/rejected`. Port existing notification writes to
consumers (receivers in `AppConfig.ready()`, dedupe via `event_id` — the
established pattern). Add the two missing user-facing notifications while at it:
removed member, role-changed member.

## MEDIUM

**M-1 · Audit + event settings changes** — move `CommunityUpdateView` writes into
`CommunityService.update_settings`; `AuditService.log` the diff (old→new per
field).
**M-2 · Join-request history (G-10/G-11)** — allow requester `cancel`; preserve
decisions (drop row-reuse: partial unique index on PENDING per pair, new row per
request cycle); optional 30-day auto-expiry task.
**M-3 · Tenant check in joins (G-13)** — `join_community`/`request_to_join`
compare `tenant_for_user(user)` to `community.tenant`; refuse + audit mismatch.
Trivial now, mandatory before P6-04 activates real mapping.
**M-4 · Deactivated users excluded from authority math (G-9)** —
`active_admin_count`, guards, and `community_role` filter `user__is_active=True`.
**M-5 · Pagination** — cursor-paginate members, discover, my-communities (reuse
ADR-0016 cursor pattern). Cap page sizes.
**M-6 · Throttles** — DRF scoped throttles on invite lookup and join-request
create.
**M-7 · Tier check on finance role actions (G-14)** — policy resolver denies
`community.finance.manage` to non-Tier-1 actors (KYC revoked ⇒ finance admin
suspended automatically).

## LOW

**L-1** REST cleanup: PATCH/DELETE on `/<id>/`, deprecate `/update/`, `/delete/`
paths (keep old routes one release).
**L-2** Notify "community has no treasurer" on treasurer loss (advisory, G-6).
**L-3** Photo-orphan cleanup job (reuse `files.purge` pattern).
**L-4** Declare retention policy for community audit/activity rows in docs
(≥7 years financial-adjacent).

## TECHNICAL DEBT

**TD-1** All writes through `CommunityService` (mute/update/delete out of views);
adopt as review rule.
**TD-2** `Contribution.community` nullable+CASCADE → nullable+PROTECT (with CR-1).
**TD-3** Membership history: append-only `MembershipEvent` (join/leave/role/ban
with actor) — the `CaseEvent` pattern; unlocks "who was treasurer in March".
**TD-4** Test additions enumerated in Backend Audit §8.

## FUTURE SCALE (build on evidence, not speculation)

**FS-1** Denormalised `member_count` maintained from H-5 events; annotate list
queries meanwhile.
**FS-2** Notification fan-out consumer batching for member-wide events (first
needed by announcements, if ever built).
**FS-3** Search: move community FTS to indexed search only when query latency
says so.
**FS-4** RBAC evolution path (RBAC §6): delegation setting → capability-set
resolver behind the same `require()` API. Design doc first.
**FS-5** KYB / community verification as a `VerificationCase` type
(`subject_type='Community'`) — schema already ready (Phase A); no Communities
changes required beyond displaying case outcome.

---

### Suggested sequencing

1. **Sprint 1 (safety)**: CR-1, CR-2, H-1, H-2 — everything that prevents
   indefensible states. All small, all testable.
2. **Sprint 2 (governance integrity)**: H-3, H-4, M-1, M-4, M-6.
3. **Sprint 3 (eventing)**: H-5 + M-2 + the two missing notifications; FS-1
   counter riding on the new events.
4. **Anytime fillers**: M-3, M-5, M-7, L-*, TD-1/TD-2.

Nothing here is a rewrite; every item reuses an existing platform pattern
(lifecycle enums + service chokepoints, outbox events, append-only history,
policy table). The module's discipline makes the remediation cheap — which is
exactly why it should be done now, before scale makes the same fixes expensive.
