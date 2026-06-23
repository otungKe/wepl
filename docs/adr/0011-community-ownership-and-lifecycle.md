# ADR-0011: Community ownership transfer & the last-admin invariant

- **Status:** Accepted (ownership transfer + last-admin guard implemented in `apps/communities/`)
- **Date:** 2026-06-23
- **Relates to:** Platform Hardening Review §2.3 + Action Plan P0 #3; builds on ADR-0009.

## Context

A community's ownership is a plain `Community.created_by` FK and admin status is
`CommunityMembership.role == 'admin'`. The review flagged two data-loss / lockout risks:

1. **No ownership-transfer flow.** If the owner left or deleted their account, the
   community could be stranded with an owner that no longer participates — and no
   sanctioned way to hand control to someone else. (`created_by` is `on_delete=PROTECT`,
   and account deletion *anonymises* rather than hard-deletes, so the row survives but
   points at a dead account — an **orphaned-owner** state with no remedy.)
2. **No "last-admin" invariant** — nothing stopped removing/demoting the final admin,
   leaving a community **unadministrable**.

## Decision

Treat ownership and admin-population as **invariants enforced in the service layer**,
authorized through the ADR-0009 policy.

- **`community.ownership.transfer`** capability (creator-only; superusers may also act)
  was reserved in the community policy in ADR-0009 and is now used by a real
  `CommunityService.transfer_ownership(actor, community, membership_id)`:
  - the new owner must be an **active member**; transferring to a non-member or to the
    current owner is rejected;
  - the new owner is **promoted to admin**, and the **former owner is kept as an admin**,
    so a transfer can never reduce the community below one admin;
  - the row is `select_for_update`-locked to serialise concurrent transfers; the action
    is logged to the activity feed and notifies the new owner.
  - Because superusers bypass the policy (platform operators), this is also the
    **remedy for an orphaned-owner community**: support can reassign ownership.
- **Last-admin invariant** (already enforced, now locked in by tests): `leave_community`
  refuses the last admin, `assign_role` refuses demoting the last admin, and the owner
  cannot be removed by `remove_member`.

## Consequences

- **+** Ownership can always move; communities can't become permanently orphaned or
  unadministrable. Operators have a recovery path.
- **+** Authorization for the new action is declarative and reuses the policy + its tests.
- **−** Ownership is still a single FK (not a multi-owner model); adequate for now.

## Scope & deferrals

This ADR delivers the **P0 invariants** only. The broader "community roles, ownership &
lifecycle" surface from the review is **explicitly deferred** to follow-ups, each its own PR:

- **Soft-delete / archive** state (vs. today's hard delete) + a retention job that checks
  for financial history before destruction.
- **Tenant-scoped slugs** for shareable URLs / to avoid id enumeration.
- **Richer role capabilities** (treasurer/officer distinct permission sets) — the policy
  matrix is the place to add them without new inline checks.
- **Discovery indexing/ranking** (see the Search ADR).
- Wiring **account deletion** to auto-transfer or block when the user owns communities
  (the transfer primitive this ADR adds is the building block).

## Alternatives considered

- **Auto-promote the longest-tenured admin on owner loss.** Rejected as the *primary*
  mechanism: implicit ownership changes surprise users; an explicit, audited transfer
  (plus operator override) is clearer. Auto-promotion can be layered on later for the
  account-deletion path.
- **Multi-owner model.** Deferred — larger change than the P0 risk requires.
