# Communities — Integration Audit

Module-by-module review of every seam Communities touches. For each: what the
integration is, whether ownership sits on the right side, and the defects found.

---

## Users / Profiles / Tiers
- **Entry gates**: `AccessPolicy.gate` (Tier-1) on create/join/request/conversation
  creation — the tier system (ADR-0022) is applied consistently at community
  boundaries, and money paths re-check independently. **Correct layering**: identity
  rules live in `users`, communities only *call* them.
- **Defect (G-9)**: platform-level `User.is_active=False` does not propagate into
  community authority math (deactivated users count as active admins, hold roles,
  block last-admin guards).
- **Defect (G-14)**: KYC revocation (now a real transition in the Verification CMS)
  does not affect held community roles; policy resolver could require Tier-1 for
  `community.finance.manage`.
- **Ownership verdict**: correct. No user data duplicated into Communities.

## Finance (contributions / welfare / shares / advances / ledger / controls)
- **Ownership verdict**: **correct and worth defending** — Communities *orchestrates*
  (bootstraps funds at creation, sets `contribution_permission`, provides the
  `finance.manage` rank, hosts cooling-off policy), while the finance module owns
  every financial object and the ledger owns every balance. No balance, total, or
  counter lives on Community. This is the right bounded-context split; resist any
  future "community treasury summary column".
- **The one broken seam**: deletion. Finance rows FK-CASCADE from Community
  (`Contribution.community`, `WelfareFund.community`, `SharesFund.community`), so
  the orchestrator can destroy the financial module's records while the ledger's
  journal lines live on with dangling `context_type/context_id`. The books stay
  balanced but become unexplainable. **PROTECT + archive lifecycle** is the fix
  (Domain Audit D-1, Business Rules G-12).
- **Cooling-off**: `check_cooling_off` is imported by welfare, advances, and
  disbursement services — policy owned by Communities, enforced by finance at the
  action. Right direction of dependency (finance → communities for *policy*,
  never the reverse for *money*). Note the rejoin-clock bug (G-4) undermines it.
- **Controls**: `LimitRule` has no per-community scope; a community freeze
  (suspension) has no enforcement hook today. When the lifecycle lands, the
  contribution-creation gate and the posting-path controls need a
  "community is active" check — one `require`-style call at the finance entrances.

## Verification Centre
- Communities have no verification state — **accepted** as roadmap (KYB is a
  declared future case type; `VerificationCase` was already generalised with
  `subject_type/subject_id` in Phase A, so *when* organisation verification arrives
  it attaches without touching Communities' schema: a case with
  `subject_type='Community'`).
- Leader/treasurer verification: implicitly Tier-1 (they're members). No
  *re*-verification hook (G-14).
- **Ownership verdict**: correct — verification stays in the Verification Centre;
  Communities must only ever *reference* a case outcome, never store its own
  trust flags. Trust scoring, if ever built, is a projection from case history,
  not a Community column.

## Chat (conversations)
- `Conversation.community` FK, membership enforced at creation via the community
  policy (`community.view`). Chat data wholly owned by conversations. **Correct.**
- Gaps (product-level, flagged not prescribed): any member can create topics (no
  role gate or per-community setting); no announcement channel; no system messages
  on membership events (join/leave/role changes are invisible in chat); financial
  discussions have no linkage to contributions (a message can't reference a fund).
- Integration defect: community CASCADE deletes all conversations/messages —
  acceptable only once deletion is restricted to never-funded shells.

## Notifications
- All community notifies are synchronous `NotificationService.create` calls; the
  module emits **no outbox events** (Backend Audit §2). Events that *should* exist
  (each maps to a current or obvious consumer):

  | Event | Emitted today? | Notes |
  |---|---|---|
  | `community_created` | ✗ (activity only) | metrics, search, ops dashboards |
  | `member_joined` / `member_left` | ✗ (sync notify + activity) | counters, chat system msgs |
  | `join_request_created/approved/rejected` | ✗ (sync notify) | |
  | `member_removed` | ✗ (**no notification at all to the removed user** — silent removal) | audit exists; user-facing gap |
  | `role_changed` | ✗ (audit only, target user not notified) | |
  | `ownership_transferred` | ✗ (sync notify to new owner only; old owner + members unnotified) | |
  | `community_settings_changed` | ✗ (nothing at all — not even audit) | security-relevant |
  | `community_archived/suspended` | n/a until lifecycle exists | |

- **Recommendation**: event-driven via the outbox for everything above;
  notifications become consumers. Synchronous writes are acceptable only for the
  actor's own confirmation.

## Activity feed
- Records: created, joined, left (private), ownership transferred. Missing:
  role_changed, member_removed (deliberate? removal in the feed is arguably
  hostile — decide explicitly and document), settings changes.
- Visibility enum used correctly (COMMUNITY vs PRIVATE). Ownership correct
  (activity app owns the feed; communities call `ActivityService.record`).

## Audit log
- `AuditService.log` on: role_changed, member_removed, ownership_transferred,
  community.deleted (pre-delete, identity captured). Good.
- Missing audit: settings changes (join_policy/invite_permission/max_members/
  cooling_off — all governance-relevant), join approvals/rejections (currently
  reconstructable from the request row, but that row is overwritten on
  re-request — G-11).
- Immutability: `AuditEvent` is append-only ✓. Retention: no policy declared
  anywhere; for financial-adjacent audit rows adopt "retain ≥ 7 years" (Kenyan
  record-keeping norms) as an explicit statement rather than an accident.

## Discovery & Search
- Discover: public-only ✓, no pagination ✗.
- Federated search: public + own memberships, tenant-scoped when pinned ✓ — this is
  the *correct* privacy model and it lives in the search app (right owner).
- Back Office federated search (`backoffice/search.py`) spans communities for
  operators — separate surface, capability-gated ✓.

## Media
- `community_photo` ImageField → R2 now that USE_S3 is enabled. No versioning
  needed (not evidence). Orphaned objects on photo replacement are tolerable
  (storage never overwrites); a cleanup job is Low priority.

## Tenants
- Stamped at creation, PROTECT, guarded on detail reads. Join paths not
  tenant-checked (G-13) — must land with P6-04. RLS covers ledger tables; community
  tables rely on app-level guards, which is the documented interim (P6-05).

## Back Office
- Capabilities `communities.view/manage` exist in the RBAC map with no console
  module behind them yet. When built, every ops mutation must route through
  `CommunityService` (not ad-hoc ORM in ops views) and `record_action` — the
  Verification Centre set the pattern. The missing lifecycle (suspend/archive) is
  the first thing an ops module will need and currently cannot have.

## Reminders / standing orders
- Community-scoped financial reminders exist in their own app, fire via beat ✓.
  With no lifecycle, reminders for dead communities run forever (G-7).

---

### Boundary verdict table

| Seam | Ownership | Verdict |
|---|---|---|
| Finance objects | contributions/ledger | ✓ correct — fix only the CASCADE |
| Balances | ledger only | ✓ sacrosanct |
| Chat | conversations | ✓ |
| Feed/audit | activity/audit | ✓, coverage gaps |
| Notifications | notifications | mechanism wrong (sync, no events) |
| Verification/trust | verification (future KYB case type) | ✓ by design |
| Search/discovery | search app | ✓ |
| Tenancy | tenants app guards | ✓ interim; service-level join check pending |
| Policy/RBAC | communities policy table via core.policy | ✓ exemplary |
