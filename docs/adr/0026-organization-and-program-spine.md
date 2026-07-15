# ADR-0026: Organization spine — every participant is an Organization

- **Status:** Accepted (Phase 0 shipped — Organization + Program spine merged)
- **Date:** 2026-07-13
- **Deciders:** Platform strategy review (see `docs/strategy/organization-os.md`)

## Context

Wepl has been positioned as a Community OS, with external "providers" expected
to integrate through a marketplace. The strategy review concluded that the
provider/marketplace split is an artificial architectural concept: a chama, a
SACCO, a church and a wealth manager are the same thing at different scales —
**an organization with members, money, and rules** — and what made a "provider"
special was never its nature but a *relationship* (it offers a program; others
subscribe).

The full evaluation, including the risks (platform trap, regulatory
reclassification, the Bank-archetype fantasy) and the phased go-to-market, is in
`docs/strategy/organization-os.md`. This ADR records the structural decision and
the Phase 0 implementation shape.

Ground truth today:

- `tenants.Tenant` is the hosting/isolation boundary (RLS). Many communities
  share the `default` tenant; a hosted institution gets its own.
- `communities.Community` is the member-money organization in all but name:
  members, roles, lifecycle, funds, governance.
- `Contribution` / `WelfareFund` / `SharesFund` are three parallel
  implementations of one concept (three FKs on `FinancialTransaction`, a
  `fund_type` enum in the ledger, triplicated settlement routing that Moves 1–2b
  consolidated).

## Decision

**One platform. Every participant is an Organization, differentiated by
archetype and granted capabilities, offering Programs, connected by
Subscriptions, settled on the shared ledger.** Adopted as the *domain model*;
go-to-market stays vertical (chamas now, SACCOs next) per the strategy doc.

Phase 0 lands the spine additively, without changing user-facing behaviour:

1. **`organizations.Organization`** — the participant spine. Thin by design:
   `uid` (UUIDv7, the external handle per ADR-0025's identity philosophy),
   `name`, `archetype` (starts with only `community`; archetypes are *earned*),
   `tenant` FK (hosting boundary — an attribute, never a hierarchy), timestamps.
   `Community` gains a OneToOne to it (the archetype *profile* pattern: the
   Organization is the general thing, Community carries the archetype-specific
   detail). Every existing community is backfilled; `create_community` creates
   the Organization at birth.
2. **`Program`** (next increment) — the registry spine over the three fund
   models: each fund row gets a Program (organization, program_type, status).
   The ledger's `(fund_type, fund_id)` account anchoring is untouched; Program
   generalizes `fund_type` from enum to entity so new surfaces enumerate one
   concept.
3. **Capability layer** (shipped, `organizations/capabilities.py`) — the
   code-defined map that makes "archetype selects a capability bundle" real: a
   universal kernel every org holds, regulated capabilities (deposit-taking,
   lending, fund distribution, clearing) as compliance-gated vocabulary, and per
   archetype a `bundle` (granted today) within a `ceiling` (may *ever* hold).
   The community ceiling equals the kernel — a chama can never be granted a
   regulated capability. `ensure_program` is the first checkpoint (inert for the
   community archetype, load-bearing once a narrower bundle exists). No per-org
   grant store yet: with one archetype whose bundle equals its ceiling, the
   bundle *is* the grant — the store lands with the first regulated archetype.
4. **Subscription / Relationship** (Phase 1) — the org↔program edge that
   replaces "Provider", built against the first real counterparty partnership.

Rules that keep the spine honest:

- **Archetype is metadata, not taxonomy** — no `if org.archetype == …` branches
  in domain logic; archetypes select capability bundles and governance profiles.
- **No tenant hierarchy** — internal structure is org units inside a tenant;
  related organizations are separate tenants joined by relationship edges.
- **Capability enablement is a compliance workflow**, not a settings toggle;
  the archetype is the ceiling that cannot be exceeded.
- **RLS parity** — every new tenant-columned table (starting with
  `organizations_organization`) carries the standard isolation policy (C-1).

## Consequences

- **+** The provider/marketplace concepts are retired before they are built —
  replaced by Organization + Program + Subscription over the existing ledger.
- **+** The three-fund duplication gets a unification target (Program) that the
  settlement work (Moves 1–2b) already prepared.
- **+** KYB, capability grants and governance profiles all reuse proven
  machinery (`VerificationCase`, `capabilities.py`, transition tables).
- **−** Two names for one thing during transition (Community + Organization)
  until archetype #2 justifies moving shared fields up the spine.
- **−** The clearing spine (cross-org money) is deferred to Phase 1 and carries
  the heaviest regulatory weight (PSP licensing posture) — it must be a
  deliberate decision, not an accretion.

## Alternatives considered

- **Provider as a separate first-class concept + marketplace.** Rejected — it
  duplicates membership/roles/documents/audit for one participant class and
  models a relationship as a party.
- **Organization replaces Tenant outright (1:1).** Rejected for now — thousands
  of chamas legitimately share the default tenant; forcing tenant-per-org would
  explode RLS overhead with no isolation benefit at chama scale. Convergence
  stays open for operational archetypes (a SACCO org gets its own tenant).
- **Big-bang rename of Community → Organization.** Rejected — the spine +
  profile pattern delivers the model without breaking the API/mobile surface;
  fields migrate up the spine when a second archetype actually needs them.
