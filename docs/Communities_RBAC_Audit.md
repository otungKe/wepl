# Communities — RBAC Audit

Roles, permissions, hierarchy, leaks, and extensibility. The policy engine
(ADR-0009, `apps/core/policy` + `communities/policies.py`) is the subject; the
verdict on the *mechanism* is positive, on the *matrix* mixed.

---

## 1. The model

One effective rank per actor per community:

```
creator (4) > admin (3) > treasurer (2) > member (1) > outsider (0)
```

Actions declare a minimum rank in a single table (`_MIN_RANK`); resolution is one
comparison; unknown actions **fail closed** (raise). All call sites use
`require()`/`can()`. There are no residual inline `role ==` checks in views or
services. This is the strongest RBAC implementation in the customer-facing codebase
and the pattern other modules should copy.

Current matrix:

| Action | Min rank |
|---|---|
| community.view | member |
| community.members.view_all | admin (layered with `member_list_visibility`) |
| community.update | admin |
| community.join_request.review | admin |
| community.finance.manage | treasurer |
| community.member.assign_role | creator |
| community.member.remove | creator |
| community.delete | creator |
| community.ownership.transfer | creator (+ platform operator escape hatch) |

## 2. Role-by-role assessment

- **Owner (creator)** — a *pseudo-role from an FK*, not a membership attribute.
  Powers: everything, exclusively member management + delete + transfer. Two
  structural risks: (a) owner-membership divergence — the owner can leave and
  remain rank-4 from outside (Business Rules G-1); (b) single-human bottleneck —
  in a 5,000-member chama, only one person can change any role or remove anyone.
  That is a deliberate ADR-0009 choice for v1; it will not survive real
  communities. The escape valve (delegate member-management to admins via a
  community setting, or introduce explicit grants) should be designed before
  support tickets force it.
- **Admin** — settings, join review, plus *implicitly* everything treasurer has
  (rank 3 ≥ 2). See §3 separation-of-duties.
- **Treasurer** — exactly one grant: `finance.manage`. Correctly scoped; cannot
  touch membership or settings. ✓ least-privilege done right.
- **Member** — view + participate; contribution creation depends on the
  community's `contribution_permission` setting layered on top ✓.
- **Guest / outsider** — rank 0; may view public communities, look up invite
  codes, request to join. No leaks found in read paths.
- **Pending member** — *not a role*, just a JoinRequest row. Correct — pending
  users hold zero authority and appear nowhere in member lists.
- **Moderator / Secretary / Committee** — absent. Not needed until chat moderation
  or meeting-minutes features exist. The rank table extends trivially (insert a
  rank), which is the design's key virtue: adding a role is data, not code.

## 3. Separation of duties — the fintech question

Admins implicitly hold treasury power (`rank admin ≥ rank treasurer`). In a
financial platform this means **whoever manages people also manages money**. Today
the blast radius is bounded because the ledger enforces its own invariants and
disbursements are vote-gated (`voting_threshold` on contributions — governance
lives at the money object, which is the real control). But two SoD gaps deserve
explicit decisions:

1. Should a community be able to *opt into* "treasurer-only finance" (admins
   excluded)? The linear rank model cannot express it — it would need either a
   capability-set model per role or an exception rule. Flag for the roadmap;
   do not build speculatively.
2. `contribution_permission=admins` labels itself "Admins & Treasurers only" and
   maps to `finance.manage` — consistent ✓.

The platform-side SoD (ops maker-checker on money actions) is a Back Office
concern already on that roadmap; nothing needed here.

## 4. Permission leaks found

- **`invite_permission` is dead configuration (HIGH)** — defined
  (`creator/admins/members`), editable via `community.update`, and enforced by
  *nothing*. `CommunitySerializer.get_invite_code` returns the code to any active
  member. Every community that set "Creator only" is silently running "any
  member". Fix at the serializer/endpoint with a `can`-style check that reads the
  setting (the policy docstring already prescribes exactly this layering); add a
  rotation endpoint so historical leakage is recoverable.
- **Departed-owner authority (HIGH)** — rank 4 derives from `created_by`
  regardless of membership (`community_role` checks the FK *before* membership).
  An ex-member owner retains full control; combined with G-1 this is both a leak
  (outsider with power) and a lockout (insiders without it). Rule fix, not
  mechanism fix.
- **Deactivated users retain rank (MEDIUM)** — `community_role` does not check
  `user.is_active`; a platform-banned user still *counts* as admin for guard math
  (they cannot authenticate, so cannot act — the leak is in the counting, which
  can deadlock last-admin protections). Exclude inactive users from
  `active_admin_count()` and guards.
- **No self-service escalation paths found** ✓ — role changes are creator-only;
  approve-join cannot set a role (always member); rejoin resets role to member;
  transfer promotes explicitly and keeps the old owner at admin (never silently
  higher).

## 5. Ops (staff) RBAC over communities

Separate system, correctly separate: `ops:*` capabilities
(`communities.view/manage`) in `backoffice/capabilities.py`, enforced with
`RequireCapability`, StaffAccount identity, `record_action` audit. The
platform-operator escape hatch inside `community.ownership.transfer` is the only
place customer-policy and ops-policy meet, and it is explicit and documented
(orphaned-community recovery). ✓

## 6. Extensibility verdict

The rank table is the right v1: one file, data-driven, fail-closed, auditable at a
glance. Its known ceilings, in the order they will be hit:

1. **Delegation** (owner shares member-management with admins) — needs either
   per-community overrides of `_MIN_RANK` entries or named grants. Design when the
   first large community complains, not before.
2. **Non-linear roles** (a treasurer who is *not* subordinate to admins;
   a moderator with chat power but no finance) — breaks the single-rank premise;
   solvable with capability *sets* per role while keeping the same `require()`
   call sites. The call-site API is future-proof; only the resolver would change.
3. **Custom roles per community** — far future; resist until multi-role
   capability sets exist, or the table stops being auditable.
