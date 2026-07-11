# Program / 63 — Future Evolution

> The ten-year view: where Wepl goes after the [roadmap's](60-roadmap-and-milestones.md)
> named phases, and the technical evolutions that become possible — or necessary —
> as it grows. This chapter is deliberately more speculative than the rest of the
> handbook; it states *directions and their preconditions*, not commitments. Each
> direction that hardens into a plan earns an [ADR](64-decision-log.md) and a
> roadmap phase.

---

## The through-line

Every evolution below is enabled by the *same* structural bet the platform already
made: **one immutable book of record entered through one door, with everything else
pluggable and disposable.** Wepl does not need to be re-architected to grow; it needs
to have *more plugged into* the core it already has. That is the definition of an
operating system, and it is why this chapter can be ambitious without being reckless.

## Direction 1 — From "a Financial OS Wepl runs" to "the Financial OS others run on"

The BaaS endgame ([Phase 7](../../roadmap/PHASE-7-baas.md)) is the pivot. Its
technical shape is already largely built:

- **Webhooks-out are just external outbox consumers** — the durable eventing of Phase
  2 *is* the webhook engine ([Eventing](../architecture/26-eventing-architecture.md)).
- **The sandbox is `FakeProvider` behind a tenant** — the test seam becomes a product.
- **Money still moves only through `post_journal()`** on the tenant's ledger — the
  public API is just another caller of the one door (**P-2**).

**Precondition:** exhaustive tenant-isolation testing and per-tenant API-key scoping
(R11) *before* any external traffic. The evolution is not "build BaaS"; it is "prove
isolation, then expose what already exists."

## Direction 2 — Service extraction along pre-drawn seams

Wepl is a [modular monolith](../architecture/22-module-boundaries.md) *by choice*, to
keep the money-and-event transaction local. If scale ever demands a split, the seams
already exist and only three are clean cuts:

1. **The ledger as a service** — it depends on nothing above it (Rule 1), the
   cleanest possible extraction.
2. **The ops/backoffice plane** — already a separate deployment and bounded module.
3. **Tenant sharding** — a horizontal split along the tenant boundary, not a
   functional decomposition.

**Precondition:** a measured need (E-15) — we do not split for fashion. The
evolution is "the seams stay clean so we *can* split," not "we will."

## Direction 3 — Mechanized boundary enforcement

Today the [dependency rules](../architecture/22-module-boundaries.md) are enforced by
CI grep-guards (for the biggest sins) and by review (for the rest). The evolution is a
**static import-contract** (an `import-linter`-style tool) that fails the build if the
ledger imports a product, or a module reaches past a port. This turns "Rule 1" from a
reviewed convention into a mechanized invariant — the same move that made the money
door safe, applied to module boundaries.

## Direction 4 — The compliance and treasury layer (Phase 8)

AML monitoring, financial-crime detection, treasury management, and data residency
([Phase 8](../../roadmap/PHASE-8-enterprise-compliance.md)) all install at the
chokepoint the platform already has:

- **AML/velocity monitoring** hangs off the one money door, beside the existing
  controls (Phase 3) — one place, not scattered.
- **Treasury** becomes safe to pursue *because* the ledger makes the float position
  exactly knowable ([Business Model](../product/04-business-model.md)); it is gated on
  the controls that make it lawful, never rushed ahead of them.
- **Data residency** extends the tenant boundary plus Neon's region model
  ([Data Architecture](../architecture/24-data-architecture.md)) to pin a tenant's
  data to a jurisdiction.

**Precondition:** the regulatory/licensing workstream (R13) — a business/legal effort
the architecture is *ready* for but cannot substitute for.

## Direction 5 — More rails, more currencies, more products (breadth)

The steady-state growth of an operating system is breadth absorbed by a stable core:

- **New rails** (bank, card, other mobile-money, cross-border) — each a
  `PaymentProvider` adapter (**P-17**), proving the port by *not* touching financial
  logic.
- **New currencies** — data, balanced per-currency by the same mechanism (Phase 5).
- **New collective-money products** — new [posting recipes](../domain/12-financial-architecture.md)
  and product services calling the one door, not new balance subsystems. Richer
  governance primitives (weighted votes, multi-signatory payouts,
  [Governance](../domain/13-governance-architecture.md)) drop into the centralized
  policy.

The measure of success is the [Vision](../product/01-vision.md)'s: **a second,
structurally different money product stood up in days, not a quarter.**

## Direction 6 — Intelligence on top of an immutable, legible ledger

A provable, fully-legible ledger of collective money is an unusually clean substrate
for analytics and (carefully) ML: credit scoring for advances, fraud/AML signals,
liquidity forecasting, member insights. The evolution here is **strictly
read-side**: intelligence reads from projections and the immutable log; it *never*
becomes a source of money truth (**P-1/P-3**) and *never* moves money except by
proposing an action that still goes through the one door with governance and controls
intact. The ledger's cleanliness is what makes trustworthy intelligence possible —
garbage-in is not a risk when the "in" is a provably-conserved book of record.

## Direction 7 — Deeper offline and resilience for the real user

As Wepl reaches more users on worse networks, the [mobile](../frontend/41-mobile-architecture.md)
evolution is richer offline tolerance and reconciliation — always with the same rule:
**local state is a projection, never money truth** (**P-3**), and money confirmation
is never optimistic (**P-16**). Resilience grows; the honesty invariants do not bend.

## Direction 8 — The handbook and the record evolve with the system

The least glamorous evolution and one of the most important (R14): this handbook, the
ADR corpus, and `CLAUDE.md` stay the durable memory of *why*. As decisions change,
new ADRs supersede old ones and chapters are revised in place
([Documentation Standards](../engineering/35-documentation-standards.md)). The
platform's ability to onboard the engineer of 2035 is itself a feature to be
maintained.

---

## The invariants that must survive every evolution

No matter how far Wepl evolves, these do not change without a superseding ADR that
consciously repeals them ([Charter](../00-charter.md)):

- **One book of record; one money door** (**P-1/P-2**).
- **Immutable truth, disposable projections** (**P-3/P-8**).
- **Conservation is provable — trial balance zero, always** (**P-6**).
- **Rails, currencies, products, and intelligence plug in; the core does not bend to
  them** (**P-17**).
- **The customer/operator split, and honest failure** (**P-12/P-16**).

Everything above is *addition* to a core that stays fixed. That is the whole promise
of building a Financial OS rather than a financial app: **the future is things
plugged into the core, not rewrites of it.**

---

*Continue to the [Decision Log](64-decision-log.md).*
