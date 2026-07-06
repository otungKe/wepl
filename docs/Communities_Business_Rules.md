# Communities — Business Rules Inventory & Gap Register

Two halves: the rules that **exist and are enforced** (with their enforcement point,
so regressions are findable), and the situations where the backend currently has
**undefined or wrong behaviour**. Gaps are stated as "what happens if…" with the
observed answer.

---

## Part 1 — Enforced rules (inventory)

### Creation
| Rule | Enforcement |
|---|---|
| Only Tier-1 (KYC-approved) users create communities | `AccessPolicy.gate` in `create_community` |
| Creator becomes an active ADMIN member atomically | same transaction |
| Community is stamped with its tenant at birth | `tenant_for_user` (stub → default tenant until P6-04) |
| Welfare/Shares funds bootstrap iff flags set; share price defaults 100.00 | `create_community` |

### Joining
| Rule | Enforcement |
|---|---|
| Private communities cannot be joined directly — only via request→approval | `join_community(_approved=False)` raises |
| Join policy: `open` joins directly, `request` requires review, `invite_only` requires the code path | `JoinCommunityView` + invite endpoints |
| Member cap enforced under a community row lock (no over-cap race) | `join_community` `select_for_update` |
| Tier-1 required to join / request | `AccessPolicy.gate` |
| Re-join reactivates the old row **as plain member** (no role resurrection) | `join_community` reactivation path |
| Join is idempotent for existing active members (no duplicate notifications) | early return |
| One pending request per (user, community); re-request re-opens a decided one | `request_to_join` |
| Only admins review join requests; double-review blocked under row lock | `action_join_request` + policy `community.join_request.review` |

### Leaving / removal / roles
| Rule | Enforcement |
|---|---|
| Last active admin cannot leave | `leave_community` guard |
| Last admin cannot leave while any active contribution has `voting_threshold='admins'` (withdrawal deadlock guard) | `leave_community` — the single most thoughtful rule in the module |
| Last admin cannot be demoted | `assign_role` guard |
| Creator's own role cannot be changed; owner cannot be removed | `assign_role` / `remove_member` guards |
| Role assignment & member removal are creator-only, and audited | policy rank CREATOR + `AuditService.log` |
| Ownership transfer: owner-only (or platform operator), new owner must be an active member, gets ADMIN, former owner retained as ADMIN (no admin-count regression), audited + notified | `transfer_ownership` (ADR-0011) |

### Financial interface
| Rule | Enforcement |
|---|---|
| Contribution creation respects `contribution_permission` (admins+treasurers vs any member) | `contributions/views/core.py` via `can("community.finance.manage")` |
| Cooling-off blocks welfare claims / emergency advances / disbursement votes for `cooling_off_days` after joining | `check_cooling_off` called from welfare, advances, disbursement services |
| Fund management gated at treasurer rank or above | policy `community.finance.manage` |
| `max_members` cannot be set below the current active count | `CommunityUpdateView` |

### Visibility
| Rule | Enforcement |
|---|---|
| Private community detail hidden from non-members | `CommunityDetailView` |
| Discover lists public communities only | `DiscoverCommunitiesView` `is_private=False` |
| Search returns public + own-member communities only, tenant-scoped when pinned | `search/services._communities` |
| Full member roster respects `member_list_visibility` | `CommunityMembersView` |
| Invite code hidden from non-members | serializer `get_invite_code` (but see G-5) |
| Cross-tenant access to a community refused + audited when a tenant is pinned | `guard_tenant` on detail view |

---

## Part 2 — Gap register (undefined / wrong behaviour)

Each entry: the question, **what the code does today**, and the rule that must be
decided. These are behaviour gaps, not feature requests.

**G-1 · What happens if the owner leaves the community?**
Today: allowed whenever another admin exists. The creator keeps rank-4 authority
(`created_by` FK is untouched) while no longer being a member: they can still—as an
outsider—assign roles, remove members, delete the community; meanwhile *no one
inside* can manage roles or remove members (creator-only actions). Governance is
simultaneously leaked outside and deadlocked inside.
**Required rule**: leaving as owner must force an ownership transfer first (mirror
of the last-admin guard), or leaving auto-transfers to a designated admin.

**G-2 · What happens if the owner's account is deleted/anonymised?**
`created_by` is PROTECT, so account deletion is blocked while they own communities —
which turns into a data-protection conflict (user cannot exercise deletion until
ownership is transferred). The ops recovery path exists (platform operators may
transfer ownership), but nothing *routes* an account-deletion request into it.
**Required rule**: account-deletion flow must enumerate owned communities and force
transfer/closure first, with an ops escalation path.

**G-3 · What happens when a removed member re-requests?**
Today: fully allowed. Removal is `is_active=False`; `request_to_join` re-opens their
old request; any admin can approve. No ban state, no "removed by owner" flag visible
to the reviewing admin.
**Required rule**: removal should record a reason/flag surfaced at review time; a
`banned` membership state must exist for the cases where re-entry is not acceptable.

**G-4 · What happens to cooling-off when a member rejoins?** *(defect, not gap)*
Today: `joined_at` is never reset on reactivation, so cooling-off is computed from
the original join date → instantly eligible for welfare claims/advances/votes on
rejoin. A member can leave and rejoin to keep a stale clock.
**Required rule**: reactivation must reset the cooling-off clock (either reset
`joined_at` — losing tenure history — or add `rejoined_at` and compute from the
later of the two; the latter preserves history).

**G-5 · Who may share the invite code?**
Setting `invite_permission` (creator/admins/members) exists and is editable — and is
enforced **nowhere**. The serializer returns the code to every active member. The
governance promise made to the owner in settings is silently broken.
**Required rule**: serializer/endpoint must honour the setting; add code rotation so
a leak is recoverable.

**G-6 · What happens if the treasurer is removed or leaves?**
Today: nothing breaks — admins outrank treasurer for `community.finance.manage`, so
finance stays operable. Defined and acceptable. Gap is only advisory: no
notification/audit event highlights "community now has no treasurer".

**G-7 · What happens if a community becomes dormant?**
No concept of dormancy/archive. Funds, reminders (beat jobs), standing orders and
discover listings run forever. **Required rule**: an `archived` lifecycle state that
freezes financial creation, hides from discover, and silences reminders.

**G-8 · What happens if a community must be frozen (fraud investigation, court order)?**
No suspension state and no per-community financial freeze; `LimitRule` scopes are
GLOBAL/PER_USER only. Ops today could only delete (destructive) or edit settings.
**Required rule**: `suspended` lifecycle state enforced at the contribution/posting
gate (a per-community control), ops-only, audited.

**G-9 · What happens if a suspended/deactivated *user* holds the last admin seat?**
Platform deactivation (`User.is_active=False`) blocks login but memberships ignore
it: a deactivated user still counts in `active_admin_count()`, still holds roles,
still satisfies the "another admin exists" guard. A community can be admin-locked by
a banned user. **Required rule**: define whether platform deactivation cascades into
community authority (recommended: excluded from admin-count guards; ops transfer
path for recovery).

**G-10 · What happens when a join request goes stale?**
No expiry; PENDING rows live forever and keep the requester blocked from
re-requesting elsewhere in the same community (unique row). No requester-side
cancel. **Required rule**: requester cancellation; optional TTL auto-expiry.

**G-11 · What happens to the review trail when a user re-requests?**
Prior decision (`reviewed_by/at`, REJECTED) is overwritten in place. **Required
rule**: review history must be append-only (partial-unique PENDING row, or an event
row per decision).

**G-12 · What happens on deletion when money has moved?** *(critical defect)*
Today: creator deletes; CASCADE destroys contributions, welfare funds and claims,
shares funds, conversations. The ledger's journal lines survive as orphaned truth
(their `context_type/context_id` now dangle). **Required rule**: deletion is refused
whenever any linked fund/contribution has posted movements; the exit path for a real
community is `archived`, and hard delete is reserved for never-funded shells.

**G-13 · Cross-tenant joins.**
`join_community` / invite / request paths never compare the joiner's tenant with
`community.tenant`. Harmless today (single default tenant), a real leak the day
P6-04 maps users to institutions. **Required rule**: tenant equality check inside
`join_community` (service level, not view level) so every path inherits it.

**G-14 · Verification regression of a member.**
KYC gates entry (`AccessPolicy.gate`) but nothing reacts if a member's KYC is later
revoked (the Verification CMS now supports revocation). Money-path checks re-gate on
action (tier checks at contribute/advance), which is the correct backstop — but
role-holding (admin/treasurer) survives revocation. **Required rule**: decide whether
revoked-KYC members may retain financial administration roles; recommended: block
`community.finance.manage` for non-Tier-1 actors in the policy resolver.
