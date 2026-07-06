# Communities — Backend Architecture Audit

Service layer, transactions, eventing, persistence, background work, security
mechanics, and scalability. Companion to the Domain Audit (model) and Integration
Audit (boundaries).

---

## 1. Service layer — strong discipline, one door mostly held

`CommunityService` is a genuine service layer: views never mutate domain state
directly, every mutating method is `@transaction.atomic`, and the locking is
*correct, not decorative*:

- `join_community` locks the **community** row → member-cap check is race-free.
- `action_join_request` locks the **request** row → double-approve from two admin
  taps is impossible.
- `assign_role` / `remove_member` / `leave_community` lock the **membership** row.
- `transfer_ownership` locks community **and** membership.

This matches the ledger's engineering culture and should be named as the module's
standard in review.

**Leaks around the single door** (state written outside `CommunityService`):
- `CommunityUpdateView.patch` writes governance settings directly on the model —
  settings changes are neither audited (`AuditService`) nor evented. Changing
  `join_policy` from `invite_only` to `open` is a security-relevant change with no
  trail.
- `CommunityMuteView` toggles membership state in the view (harmless, but the
  precedent is the problem).
- `CommunityDeleteView` performs the destroy itself (and is the critical-defect
  site — see Domain Audit D-1).

**Recommendation**: move update/delete into the service, emit audit entries for
governance-setting changes, and adopt "views never touch ORM writes" as a hard rule
for this app.

## 2. Eventing — the module predates the outbox and it shows

Communities uses **zero** `emit()` calls. All notifications are direct, synchronous
`NotificationService.create(...)` rows written inside the request transaction, and
`_notify_admins` loops one INSERT per admin.

Consequences:
1. **Inconsistency with ADR-0006**: the platform's rule is "domain events go through
   the transactional outbox"; Communities is the largest module not on it. There are
   no `community_created / member_joined / member_removed / role_changed /
   ownership_transferred` domain events for other modules to consume — Activity and
   Notifications are hand-wired at each call site instead.
2. **Atomicity is accidental, not guaranteed**: same-transaction Notification rows
   do roll back with the action (fine), but any consumer added later (metrics,
   search reindex, webhooks) has no event stream to subscribe to and will end up as
   another synchronous call in the request path.
3. **Fan-out ceiling**: per-admin loops are fine (admins are few); the pattern will
   be copied for member-wide announcements someday and melt a 10k-member community.
   The outbox + a fan-out consumer is the platform's own answer.

**Recommendation**: introduce the community event catalogue (see Integration Audit
§Events) via `emit()`, and let notification creation become a consumer. Do it before
Back Office dashboards start wanting community metrics — they'll need the events.

## 3. Persistence review

### Indexes & constraints — present and mostly right
- `Community(is_private, category)` serves discover; memberships indexed both ways
  (`community,is_active` / `user,is_active`); join requests `(community, status)`.
- `unique_together(user, community)` on membership: correct for the one-row model
  (defers to the Domain Audit's argument for an event trail).
- `invite_code` unique: fine. Lookup is `iexact` on an upper-cased value —
  functionally consistent (code generated uppercase).

### FK deletion semantics — the weak spot
| FK | Behaviour | Assessment |
|---|---|---|
| `Community.created_by` PROTECT | blocks user deletion | right instinct, unmanaged consequence (Business Rules G-2) |
| `Community.tenant` PROTECT | right | ✓ |
| `Contribution.community` **CASCADE** (nullable!) | community delete destroys contributions | wrong twice: cascade destroys financial context; nullable + CASCADE is an odd pair — standalone contributions survive as `community=NULL` only if never linked. Should be PROTECT (or SET_NULL with an archived-community rule). |
| `WelfareFund.community` / `SharesFund.community` CASCADE | same class of wrong | must be PROTECT |
| `Conversation.community` CASCADE | messages vanish with community | acceptable *only after* delete is restricted to never-funded shells; otherwise chat history about money vanishes too |
| `CommunityMembership`/`JoinRequest` user FKs CASCADE | membership history vanishes with user deletion | consistent with anonymisation goals, but removes the “who approved X” trail — prefer SET_NULL + label like `AuditEvent` |

### Soft delete / history
No soft deletes anywhere in the module; no historical tables. The platform pattern
(immutable events + projections) exists two apps away — reuse it rather than adding
`deleted_at` columns piecemeal. Priority order: lifecycle state on Community first
(cheap, unblocks ops), membership events second, join-request history third.

## 4. API design review

Consistent with the codebase (APIView + explicit paths), but several conventions
drift from REST and from the app's own patterns:

- **Verb-paths where methods would do**: `/<id>/update/` (PATCH) and `/<id>/delete/`
  (DELETE) instead of PATCH/DELETE on `/<id>/`. Harmless, but inconsistent with how
  `RemoveMemberView` uses DELETE on the resource path. Pick one style.
- **No pagination** on members, discover, or my-communities. Discover slices in
  Python; a 5k-member roster serialises in one response. Cursor pagination is
  needed before "hundreds of thousands of communities" is real (DRF pagination or
  the cursor pattern already used by the activity feed, ADR-0016).
- **Membership vs user IDs**: role/remove endpoints key on `membership_id` — good
  (no user-id IDOR ambiguity); requests key on `req_id` with community derived from
  the row and policy-checked — good.
- **Idempotency**: joins/leaves are naturally idempotent (get_or_create / early
  return). No Idempotency-Key needed at this layer; money paths already have it in
  the ledger. ✓
- **Bulk operations**: none exist; none needed yet. Bulk member import will
  eventually be asked for (chama migration onto the platform) — design it as a
  background job then, not a giant request.

## 5. Background work

Present: none owned by Communities (correct today — reminders and standing orders
live in their own apps; beat schedules are already defined there).

Missing (should be Celery, not request-path, when built):
- outbox fan-out consumers for community events (member-wide notifies);
- denormalised counters (`member_count`) refresh, once lists need them —
  currently every list row COUNTs members on the fly; acceptable now, a known
  N+1/aggregate hotspot at scale;
- search indexing on community rename/description change (FTS currently queries
  live tables, fine at current scale; revisit with volume);
- archive housekeeping (auto-archive dormant communities) if G-7's rule is adopted.

## 6. Security mechanics

- **AuthZ**: every view routes through `require()`/`can()` with the ADR-0009 policy
  table; unknown actions fail closed. No inline role comparisons left. This is the
  strongest part of the module.
- **IDOR**: object access is scoped (`membership_id` within community, request →
  community → policy). Detail view hides private communities from non-members.
  Members list respects visibility settings. No leaks found in the read paths
  audited. One exception: **invite_code exposure ignores `invite_permission`**
  (RBAC audit §4) — a policy leak rather than an IDOR.
- **Escalation**: role assignment is creator-only; admins cannot self-promote or
  promote others (deliberate). The inverse hole is G-1 (departed owner keeps power).
- **Tenancy**: reads guarded on the detail view via `guard_tenant` (+ audit row via
  `CrossTenantAccessAttempt` machinery). Writes (join/request) are not
  tenant-checked at the service — fine while `tenant_for_user` is a stub, must land
  with P6-04 (Business Rules G-13).
- **Rate limiting / spam**: no throttles on join-request or invite-lookup
  endpoints. `CommunityByInviteView` allows code enumeration attempts (10-hex
  space is large; still, throttle it), and `request_to_join` lets a user spam
  admins with re-requests after each rejection with no cool-down. Add DRF
  throttles; both are one-liners against existing scopes.

## 7. Scalability review

| Concern | Today | At 100k communities / large memberships |
|---|---|---|
| Member counts in list serializers | live COUNT per row | needs denormalised `member_count` maintained by events, or annotated queries |
| `active_admin_count()` per guard | COUNT on demand | fine (indexed, small) |
| Discover | table scan filtered `is_private=False` + Python slice | needs pagination + category/tenant index (exists) + eventually ranking |
| Members roster | unpaginated | cursor-paginate; 10k-member roster must never be one response |
| Notifications | sync per-admin inserts | outbox + consumer fan-out |
| Search | live FTS over communities table | acceptable; move to indexed search service only with evidence |
| Join races | solved via row locks | lock contention on *mega* open communities' join bursts — acceptable; the lock is per-community |
| Chat volume | conversations app's concern | Communities holds no message data — correctly insulated |

## 8. Test posture

35 tests cover joining policies, caps, cooling-off, role guards, transfer, and the
private-join bypass regression. Missing coverage that this audit's fixes must add:
delete-with-funds refusal, rejoin cooling-off clock, invite-permission enforcement,
owner-leave rule, request-history preservation, tenant-mismatch join refusal.
