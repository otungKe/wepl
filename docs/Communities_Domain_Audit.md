# Communities — Domain Model Audit

**Scope**: `apps/communities` and every module that references it, audited from a
business/backend/systems-architecture perspective. Grounded in the code as of this
audit — every claim cites its source. No UI commentary.

**Verdict in one line**: a *disciplined but minimal* domain — the write paths are
transactional, policy-gated, and audited to a standard most codebases never reach,
but the model itself is missing a lifecycle, a membership state machine, and an
invitation aggregate, and one critical defect (hard delete) can destroy the domain
context of money that already moved.

---

## 1. Entity inventory — what exists

| Entity | Where | Assessment |
|---|---|---|
| `Community` | `communities/models.py` | Aggregate root. Identity, tenancy (`tenant` FK, mandatory), category, privacy, fund flags, governance settings (Section A), cooling-off (Section B). Sound core. |
| `CommunityMembership` | `communities/models.py` | Role (`admin/treasurer/member`) + `is_active` boolean + `joined_at` + per-community mute. **The boolean is doing the work of a state machine** (see §3). |
| `CommunityJoinRequest` | `communities/models.py` | `PENDING/APPROVED/REJECTED` with reviewer attribution. One row per (community, requester) forever — reused on re-request, which **overwrites review history** (see §4). |
| Policy table | `communities/policies.py` | Rank-based RBAC as data (ADR-0009): `creator(4) > admin(3) > treasurer(2) > member(1) > outsider(0)`. Single resolver, fails closed on unknown actions. Good design. |
| Funds (`WelfareFund`, `SharesFund`, `Contribution`) | `apps/contributions` | Financial objects FK → Community. Correctly owned by the finance module; Communities only *orchestrates* creation at community-create time. |
| Community chat (`Conversation`) | `apps/conversations` | FK → Community; created ad hoc by any member. Correctly owned by conversations. |
| Activity / Audit | `apps/activity`, `apps/audit` | Community actions write both; coverage is uneven (see Integration Audit §Activity). |

## 2. Entities that are *deliberately* absent — and correctly so

Do not add these; ownership is right as-is:

- **CommunityTreasury / MemberBalance** — balances live in the ledger
  (`post_journal()` → `JournalLine` → derived `AccountBalance`). A balance column on
  Community would recreate exactly the mutable-cache defect ADR-0002 killed.
- **CommunityVote / Governance ballots** — disbursement votes, amendment votes and
  their thresholds live on `Contribution` (`voting_threshold`,
  `amendment_voting_threshold`, `required_approvals_for()`), which is where the
  money decision is. Communities set defaults; contributions execute governance.
- **CommunityChat models** — conversations app owns messaging; Communities is only
  a referenced scope.

## 3. Missing entities / states — the real gaps

### 3.1 No community lifecycle (HIGH)
`Community` has **no status field**. The only states are implicit: exists,
`is_private`, deleted. There is no `draft`, no `suspended` (moderation/compliance
freeze), no `archived` (dormant chama that finished its cycle), no `pending_verification`.
Every future ops action ("freeze this community while we investigate") currently has
nowhere to land except deletion. The Back Office `communities.view/manage`
capabilities exist with no lifecycle to manage.

### 3.2 Membership `is_active` boolean collapses five states into one bit (HIGH)
Left voluntarily, removed by owner, banned, never-was, and (future) suspended are all
`is_active=False` or row-absent. Consequences, all real today:

- **No ban**: a removed member can immediately re-request
  (`request_to_join` re-opens a REJECTED row) and a different admin can approve them
  back in. There is no way to say "never again".
- **No distinction for analytics/audit**: "why did this member stop being active"
  is only recoverable by cross-reading `AuditEvent`.
- **Rejoin resets the role to member** (`join_community` reactivation path) — good —
  but **`joined_at` is not reset** (`auto_now_add`, never touched on reactivation).
  `check_cooling_off` computes eligibility from the *original* `joined_at`, so a
  member who joined two years ago, left, and rejoins today **bypasses the
  cooling-off period entirely**. That is a financial-safety rule silently voided —
  a genuine business-rule bug, not a nicety. (See Business Rules §R-7.)

### 3.3 No Invitation aggregate (MEDIUM)
Invites are one static, permanent `invite_code` per community (`uuid4[:10]`).
Missing as a consequence:
- no expiry, no revocation/rotation endpoint (a leaked code is leaked forever
  unless a developer rotates it in the DB);
- no per-invite attribution (who invited whom — relevant for both growth analytics
  and abuse tracing);
- no single-use / capped invites;
- and the **`invite_permission` setting is unenforced** — see RBAC audit §4. The
  serializer hands the code to *any* active member regardless of the setting.

### 3.4 No membership history (MEDIUM)
`CommunityMembership` is one mutable row per (user, community). Role changes and
deactivations overwrite in place; the only history is `AuditEvent` (role change,
removal) — joins and leaves are Activity-only. For a financial community, "who held
treasurer authority during March" is an auditor's question the model cannot answer
directly. A `MembershipEvent` append-only trail (exactly the `CaseEvent` pattern the
Verification CMS just shipped) is the platform-consistent fix when it matters.

### 3.5 No community-level verification (ACCEPTED GAP)
Communities have no trust/verification state and no link to the Verification Centre.
This is *consistent with the roadmap* (KYB / organisation verification is a declared
future case type on the case ledger — Phase A already generalised `VerificationCase`
for it). Leader trust is enforced indirectly and correctly: `AccessPolicy.gate`
(Tier-1 / KYC-approved) guards create and join. Flagged here so the gap is a
decision, not an accident.

### 3.6 Announcements / community events (LOW)
No announcement (one-way, admin-authored) concept and no community calendar events.
`Reminder` covers scheduled financial nudges. Chat topics are peer-level. Only worth
modelling when the product asks for it; noted because the prompt asks — this is a
product gap, not an architectural one.

## 4. Aggregate boundaries & normalization

- **Community is a clean aggregate root**: memberships and join requests hang off it
  and mutate only through `CommunityService` methods that lock the relevant rows
  (`select_for_update` on community for joins/transfer, on membership for
  role/remove, on the request for review). This is the right shape.
- **Join-request identity is wrong for history**: `unique_together(community,
  requester)` + status reuse means each re-request *overwrites* `reviewed_by/at` of
  the previous decision. Either allow multiple rows (drop the uniqueness to a partial
  "one PENDING per pair" constraint) or append review events. Today an admin's past
  rejection disappears from the record the moment the user re-applies.
- **Governance settings live on the root** (join_policy, invite_permission,
  contribution_permission, member_list_visibility, max_members, cooling_off_days).
  At six settings this is fine; a `CommunitySettings` table would be premature. The
  defect is not placement but *enforcement drift* — settings exist that nothing reads
  (invite_permission), which is worse than not having the setting.
- **`created_by` doubles as "Owner"**: ownership is a *pseudo-role* derived from an
  FK, not a membership attribute. Workable (transfer exists, ADR-0011), but it means
  ownership and membership can disagree — the creator can *leave the community* and
  remain rank-4 owner (see Business Rules §R-1). The FK-as-ownership design forces
  that hole to be closed by rule, since the model won't.

## 5. Lifecycle ownership

| Transition | Owner today | Assessment |
|---|---|---|
| Create (+funds bootstrap) | `CommunityService.create_community` | Correct: Tier-1 gate, tenant stamp, admin membership, welfare/shares funds created via contributions models. |
| Join (open/approved) | `join_community` | Correct: private-bypass fix, member-cap under lock, idempotent rejoin. |
| Request → review | `request_to_join` / `action_join_request` | Correct mechanics; history-overwrite defect above. |
| Leave | `leave_community` | Correct incl. two last-admin guards (plain + contribution-deadlock). Best-in-file rule. |
| Role change / removal | creator-only service methods | Enforced + audited. Creator-only is a deliberate bottleneck — see RBAC audit. |
| Ownership transfer | `transfer_ownership` | Excellent: lock, promote new owner, retain old as admin, audit + activity + notify. |
| **Delete** | `CommunityDeleteView` → `community.delete()` | **CRITICAL DEFECT** — hard delete, creator-rank gate only, no financial guard. CASCADEs through `Contribution`, `WelfareFund` (+claims), `SharesFund`, `Conversation`/messages, activity rows. Journal lines survive in the ledger, but every domain object that explains them is destroyed. A creator can erase the financial context of a chama that moved millions. Must become: refuse when any fund/contribution has posted movements, and replace hard delete with archive (lifecycle state) + PROTECT. |
| Suspend / archive / reactivate | — | Do not exist (no lifecycle). |

## 6. Summary of domain findings

| # | Finding | Severity |
|---|---|---|
| D-1 | Hard delete cascades through financial domain objects; no posted-funds guard | **Critical** |
| D-2 | No lifecycle state machine (suspend/archive/draft) | High |
| D-3 | Membership boolean hides removed/banned/left; no ban semantics | High |
| D-4 | Rejoin keeps original `joined_at` → cooling-off bypass | High (financial-safety bug) |
| D-5 | `invite_permission` setting never enforced; static non-rotatable invite code; no Invitation entity | High |
| D-6 | Join-request row reuse destroys review history | Medium |
| D-7 | No membership history trail (role tenure unanswerable) | Medium |
| D-8 | Owner-membership divergence possible (creator leaves, stays rank-4) | High (rule gap, see Business Rules) |
| D-9 | No community verification linkage (accepted, roadmap KYB) | Accepted |
| D-10 | No announcements/community events entities | Low / product decision |
