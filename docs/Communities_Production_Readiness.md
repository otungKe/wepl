# Communities — Production Readiness Assessment

**Question**: would you deploy this backend to production?

**Answer**: **Conditionally — yes for the current, small-scale, single-tenant
reality; no for the platform this is becoming, until the Critical and High items
below are closed.** The module's engineering discipline (transactions, locking,
policy engine, audit hooks, tier gates) is production-grade. What is *not*
production-grade is a handful of business rules whose absence converts ordinary
user behaviour into data loss, governance deadlock, or silent policy violation —
and in a fintech, those are incidents, not bugs.

The deciding test: *can a non-malicious user, doing something reasonable, put the
system into a state we cannot defend to an auditor or a member?* Today, yes — four
distinct ways (C-1, H-1, H-2, H-3 below).

---

## Blocking issues (fix before real money at real scale)

**C-1 · Hard delete destroys financial context.**
`DELETE /communities/<id>/delete/` is creator-gated only and CASCADEs through
contributions, welfare funds/claims, shares funds, and all chat. Journal lines
survive with dangling context — balanced books nobody can explain. An owner
closing shop erases the community's financial record.
*Fix*: PROTECT on all finance FKs; deletion refused when any posted movement
exists; archive state as the real exit. (Domain D-1 / Rules G-12.)

**C-2 · No suspension/freeze capability.**
There is no way to stop a community — not for fraud investigation, court order,
or member protection — short of deleting it (see C-1). For a regulated-adjacent
money platform this is an operational-response gap, not a feature gap.
*Fix*: lifecycle states (`active/suspended/archived`) + a single is-active check
at the finance entrances + ops action in Back Office. (Rules G-8.)

## High — real defects, bounded blast radius

**H-1 · Cooling-off bypass on rejoin** — leave + rejoin voids the waiting period
for welfare claims/advances/votes because `joined_at` survives reactivation. A
financial-safety control that members can switch off themselves. (Rules G-4.)

**H-2 · Owner-departure deadlock/leak** — an owner may leave; they keep full
authority from outside while no insider can manage members. (Rules G-1; RBAC §4.)

**H-3 · `invite_permission` unenforced** — a governance setting owners rely on is
silently ignored; invite codes are permanent and non-rotatable. (RBAC §4.)

**H-4 · No ban semantics** — removal is freely reversible by re-request +
any-admin approval, with no flag shown to the approver. (Rules G-3.)

**H-5 · Community events bypass the outbox** — no domain events exist for any
community action; notifications are synchronous per-recipient inserts. Violates
ADR-0006 and blocks every future consumer (metrics, ops dashboards, chat system
messages). (Backend §2.)

## Medium

- Settings changes unaudited & unevented (join_policy flips leave no trace).
- Join-request review history overwritten on re-request (G-11); no requester
  cancel; no expiry (G-10).
- Deactivated users count toward admin guards (G-9).
- Cross-tenant join unchecked at service level — a P6-04 prerequisite (G-13).
- Silent removal: removed members receive no notification; role changes are not
  notified to the affected member.
- No pagination on members/discover; live COUNTs in list serializers.
- No throttles on invite lookup / join-request endpoints.
- KYC revocation does not affect held financial-admin roles (G-14).

## Low / technical debt

- View-level writes for update/mute/delete (bypass the service layer).
- `/update/`, `/delete/` verb-paths inconsistent with resource-style endpoints.
- `Contribution.community` nullable + CASCADE oddity.
- Orphaned photos on replacement; no cleanup job.
- No membership history trail (role tenure).
- Retention policy for audit/activity undeclared (adopt ≥7y for
  financial-adjacent records explicitly).

## What is already production-grade — keep it that way

- Locking discipline on every mutation (double-approve, over-cap, concurrent
  transfer all impossible).
- Policy engine: single fail-closed rank table, zero inline role checks.
- Last-admin guards, including the contribution-deadlock variant.
- Ownership transfer flow (lock, promote, retain, audit, notify).
- Tier-1 gates at every entry; money paths re-check independently.
- Correct bounded contexts: no balances, no chat, no verification state stored on
  Community; finance owns money, ledger owns truth.
- Tenancy stamped at birth, guarded on reads, RLS on the ledger beneath.

## Scale readiness (100k+ communities, millions of transactions)

Nothing in the schema blocks scale — indexes are right, locks are per-community,
money volume lands in the ledger not here. The four things that *will* degrade
first, in order: unpaginated member/discover lists → live member COUNTs in
serializers → synchronous notification fan-out → FTS over the live table. All
four have named fixes in the Implementation Plan; none requires re-architecture.

## Bottom line

Fix C-1/C-2 and H-1…H-5 and this module deserves its production badge: the
foundations are unusually sound, and every blocking item is a bounded,
well-understood change with an existing platform pattern to lean on (lifecycle →
same enum+service pattern as everywhere; events → outbox; history → the case
ledger's append-only pattern). Estimated as one focused phase of work, not a
rewrite.
