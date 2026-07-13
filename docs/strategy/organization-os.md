# Wepl Platform Strategy — The Organization Operating System

**Status:** Adopted direction (see ADR-0026 for the structural decision)
**Date:** 2026-07-13

## The Verdict

The Organization reframe is **architecturally correct and strategically dangerous**.

Correct: a community *is* an organization, "Provider" *is* an artificial bolt-on,
and the generalization is real. The codebase already knows this: the `Tenant`
model, RLS isolation, the backoffice capability map, and the ledger's
org-agnostic account tree (ADR-0025) are an embryonic Organization OS.

Dangerous: "an operating system for every organization" is the classic platform
trap — horizontalizing before winning a vertical. Salesforce extracted its
platform from CRM dominance; Shopify from merchants; Stripe from card payments.
Every enduring horizontal platform was a vertical that won first.

**Decision: adopt Organization OS as the domain model. Refuse it as the
go-to-market.** One platform; every participant an Organization; archetypes
*earned* — extracted from real duplication — not designed upfront.

## 1. What Wepl Fundamentally Is

Not "Community OS" (too narrow), not "Organization OS" (too broad — a school's
timetabling is not our business). The kernel is the ledger:

> **Wepl is the Member-Money Operating System — the system of record for any
> organization whose members pool, contribute, borrow, invest, or claim money
> through it.**

Boundary test: Wepl serves an organization if and only if its relationship with
its members is mediated by **money and governance**. A chama: entirely. A SACCO:
entirely. A church: offerings/welfare/projects. A school: fees and bursaries —
not learning management. A county: a specific revenue program — not general
administration.

## 2. Core Domain Model

| Entity | Role |
|---|---|
| **Identity (Person)** | One human, one identity, KYC'd once (`users.User` — already correct) |
| **Organization** | The participant spine. Every participant, no exceptions. Generalizes `Community` |
| **Tenant** | The *hosting/isolation* boundary (unchanged). Heavier archetypes get a dedicated tenant; light archetypes (chamas) may share one. Org→tenant is an attribute — never a hierarchy |
| **Archetype** | A curated capability bundle + regulatory ceiling + governance profile. Metadata, not taxonomy — no `if org.type == …` anywhere |
| **Capability** | An individually granted, audited permission for what an org may *do* (generalizes `backoffice/capabilities.py` to org level) |
| **Program** | A named financial arrangement an org *operates* — generalizes `Contribution` / `WelfareFund` / `SharesFund` |
| **Subscription (Relationship)** | Org↔Program or Person↔Program — **the edge that replaces "Provider"** |
| **Membership** | Person↔Organization with org-scoped roles (generalizes `CommunityMembership`) |
| **Ledger** | Unchanged. The constitution of the platform |
| **Governance Profile** | Code-defined decision model an archetype selects |

Two hard calls:

- **Provider dies as a concept.** What made ABC Wealth a "provider" was never its
  nature — it was a *relationship*: it offers, others subscribe. Model the
  relationship, not the party.
- **A Program is ledger-shaped**: terms + a chart-of-accounts template + posting
  recipes + a lifecycle + subscription rules. ADR-0025 already gives every fund a
  pool control account and member sub-ledgers; a Program is the thing that owns
  that subtree. Subscription = account creation. The ledger does not change —
  it was already general enough.

## 3. Organization Lifecycle

Registration → **KYB verification** (the `VerificationCase`/`decide()` machinery
extends directly: registration documents instead of ID photos, SASRA/IRA license
checks instead of IPRS) → configuration → **capability enablement as a compliance
workflow** (not a settings toggle; archetype = the ceiling that can never be
exceeded) → operations → **wind-down as a money process** (freeze inflows →
settle obligations → distribute per governance → final journals → statutory
ledger retention). No archetype ships without a defined wind-down recipe.

## 4. Capability Architecture

Three tiers:

1. **Universal kernel** (every org): identity, membership, roles, ledger,
   payment rails, communications, notifications, audit, documents. *This is what
   Wepl has already built.*
2. **Regulated capabilities** (compliance-gated grants): deposit-taking,
   lending, premium collection, fund distribution, payout authority tiers.
3. **Archetype bundles**: curated defaults so a chama works with zero
   configuration.

The death mode is the **inner-platform effect** — everything configurable,
nothing working out of the box. Defenses: rule of three before abstracting; the
capability matrix is never exposed to end users (only archetypes are); an
archetype ships only when a real customer segment needs it. Plugins/SDK: not
before Phase 3. API-first is the extension story until then.

## 5. Governance

Wepl already runs two governance models in production: member-democratic
(contribution voting, disbursement approvals) and staff-hierarchical (ops RBAC,
maker-checker). Generalize *that*: a **Governance Profile** is a code-defined
decision model — like posting recipes are code-defined money models — selected
by archetype, parameterized by config (quorums, thresholds). `mutual`,
`administrative`, `board`. A SACCO composes `mutual` (AGM decisions) with
`administrative` (credit-committee operations).

**No user-defined workflow engines.** Transition tables live in code, reviewed
and tested, exactly like `VALID_TRANSITIONS` today.

## 6. Marketplace → Program Catalogue

Kill "Marketplace" — it imports the wrong physics (inventory, carts, impulse).
Subscribing a chama to a money-market fund is **regulated relationship
formation**: disclosure → governance vote (exists today) → eligibility/KYB →
account provisioning → recurring settlement. Keep discovery thin (Organization
Directory + Program Catalogue); invest in the **Subscription Pipeline**.

## 7. Multi-Tenancy: the Two Hard Problems

- **No tenant hierarchy.** Branches/committees are org units *inside* a tenant;
  related organizations are separate tenants joined by a Relationship edge.
- **Cross-org money needs a settlement spine.** Today's RLS assumes each row has
  one tenant; a subscription payment belongs to two orgs. Model it like
  correspondent banking: each org's ledger records its own leg, and a
  **platform-scoped clearing context** records the inter-org transfer and
  reconciles the legs. Wepl becomes the clearing house between member-money
  organizations — that is the moat this reframe actually unlocks, and the piece
  with the heaviest regulatory weight.

Cross-org messaging/permissions: default-deny; the only channels are those a
Relationship explicitly creates.

## 8. Identity

One person, one identity, many memberships — already true; defend it.
Additions: **KYC passporting** (verify once, assert per org with member consent
— a genuine moat) and explicit **data ownership rules**: identity belongs to the
person; membership/financial data belongs to the org, per-org siloed;
cross-org sharing only by consent, only along relationship edges. The Employer
archetype is the canary: an employer must never infer an employee's chama
activity (DPA 2019 + trust collapse). Default-deny cross-org visibility is
constitutional, not a setting.

## 9. Risks (challenged honestly)

- **The Bank archetype is fantasy — cut it.** A licensed bank will not make a
  startup its book of record. The real adoption ladder: chamas → investment
  clubs → welfare groups → churches → schools (fees) → **SACCOs** (the prize:
  thousands, SASRA-regulated, underserved) → microfinance → fund *distribution*
  partnerships. Fund managers/insurers join as **counterparty organizations**
  (operate a Program, receive settlement), not operational tenants.
- **Regulatory reclassification is the existential risk.** Three thresholds:
  being a SACCO's system of record (SASRA outsourcing/IT guidelines apply to
  Wepl); being in the flow of funds between orgs (CBK PSP licensing under the
  NPS Act — decide principal vs agent deliberately); each regulated archetype
  imports a compliance regime that must be *encoded*. Archetype expansion is
  gated by compliance capacity, not engineering capacity.
- **Positioning dilution / the super-app trap.** The platform is horizontal;
  the products stay vertical ("Wepl for Chamas", "Wepl for SACCOs"). Never
  market the kernel.
- **Concentration risk.** A clearing spine makes Wepl systemically important;
  the resilience work (fail-open throttles, settlement recovery, reconciliation)
  is prerequisite, not polish.

## 10. Sequencing

Each phase is independently valuable even if the next never happens:

- **Phase 0 — rename the truth (internal only).** Organization spine over the
  existing models: `Community` becomes the first Organization archetype. Fold
  the three fund models into **Program**. Zero new markets; pays for itself in
  deleted duplication. *(ADR-0026 — in progress.)*
- **Phase 1 — first counterparty org.** One designed partnership (money-market
  fund distribution to chamas). Builds the Subscription pipeline and clearing
  spine against one real counterparty; retires Provider/Marketplace in
  production, not in slides.
- **Phase 2 — first operational archetype: SACCOs.** Where archetype /
  capability / governance abstractions get *extracted* from a second concrete
  case rather than invented.
- **Phase 3 — open the archetype platform** — only after two archetypes and the
  clearing spine are proven.

**Kill list** (explicit, so it stays killed): Bank archetype; general-purpose
government administration; user-defined workflow engines; tenant hierarchies;
plugin SDK before Phase 3; the word "Marketplace".

**One sentence:** Wepl becomes the Organization OS by never saying so out loud —
building it as the internal architecture and selling one organization type at a
time, in the order the regulators and the ledger allow.
