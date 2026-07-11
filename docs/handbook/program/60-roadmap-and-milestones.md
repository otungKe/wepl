# Program / 60 — Roadmap & Milestones

> The arc from here to a Financial OS, and how to tell when each stage is truly
> reached. This chapter is the handbook's view of the plan; the authoritative,
> checkbox-level tracking lives in [`docs/roadmap/`](../../roadmap/README.md) and its
> mirrored GitHub epics (#4–#13). Here we explain the *shape* and the *why of the
> sequencing*.

---

## The sequencing thesis

The roadmap is not a feature list — it is a **dependency order**. Its central
insight, learned from the [2026-06 audit](../../audit/2026-06-architecture-audit.md):
almost everything valuable (limits, risk, reporting, multi-currency, multi-tenancy,
BaaS) becomes *cheap* once the posting chokepoint exists, and *impossibly expensive*
before it. So Phase 0 — making `post_journal()` the one money door — comes first, and
everything else hangs off it. Building Phases 5–8 on a mutable-field core would be
"pouring the second floor before the foundation." Currency- and tenant-*awareness*
are threaded into new code from Phase 0 so the doors are left open without paying to
furnish the rooms yet.

## The phases

| # | Phase | Goal | Status |
|---|-------|------|--------|
| 0 | [Ledger-First Cutover](../../roadmap/PHASE-0-ledger-cutover.md) | Make double-entry authoritative; delete all legacy money code | ✅ Done |
| 1 | [Payment Rail Abstraction](../../roadmap/PHASE-1-payment-rails.md) | `PaymentProvider` port; M-Pesa as adapter #1 | ✅ Done |
| 2 | [Durable Eventing (Outbox)](../../roadmap/PHASE-2-eventing-outbox.md) | No lost domain events | ✅ Done |
| 3 | [Controls: Limits & Risk](../../roadmap/PHASE-3-controls-limits-risk.md) | Limits + velocity/fraud gate at the chokepoint | ✅ Done (core) |
| 4 | [Reporting & GL](../../roadmap/PHASE-4-reporting-gl.md) | Trial balance, statements, audit exports | ✅ Done (core) |
| 5 | [Multi-Currency](../../roadmap/PHASE-5-multi-currency.md) | FX-aware `Money`; per-currency balancing | ✅ Done (core) |
| 6 | [Multi-Tenancy](../../roadmap/PHASE-6-multi-tenancy.md) | Tenant boundary + isolation | ✅ Done |
| 7 | [Banking-as-a-Service](../../roadmap/PHASE-7-baas.md) | Public API, webhooks-out, sandbox, API keys | 🔴 Not started |
| 8 | [Enterprise & Compliance](../../roadmap/PHASE-8-enterprise-compliance.md) | AML, monitoring, treasury, data residency | 🔴 Not started |

Phases 0–6 are done; the platform is a working, ledger-first, multi-currency,
multi-tenant community-finance system. The remaining arc (7–8) is what turns it from
*a Financial OS Wepl runs* into *a Financial OS others run on*.

## The milestones, framed as provable claims

Milestones are stated as things you can *prove*, not features you can demo — in
keeping with [Philosophy §2](../product/02-philosophy.md) (provability over
confidence).

### M0 — One book of record (reached)
*Claim:* the double-entry ledger is the only monetary truth; the legacy single-entry
ledger and mutable balance caches are gone and CI-guarded against return.
*Proof:* the grep-guard is green; `reconcile_ledger` proves the trial balance zero.

### M1 — Rails are pluggable (reached)
*Claim:* M-Pesa is an adapter behind a port; a second rail needs no financial-logic
change.
*Proof:* money paths test end-to-end against `FakeProvider` with no Daraja
vocabulary above the port.

### M2 — No lost events (reached)
*Claim:* a domain event is never lost and never lies.
*Proof:* events are `OutboxEvent` rows in the business transaction; the relay
redelivers; consumers dedupe.

### M3 — Cross-cutting concerns at one door (reached, extending)
*Claim:* limits/risk live at the posting chokepoint; adding a new control is one
insertion point.
*Proof:* controls run inside/around `post_journal()`; overrides are audited.

### M4 — Statements from the GL (reached)
*Claim:* financial statements are generated *from* the ledger, not reconstructed.
*Proof:* `reporting.py` reads journal lines directly.

### M5 — Multi-everything core (reached)
*Claim:* a new currency is data; a tenant is isolated.
*Proof:* per-currency balancing; tenant-scoped data with isolation tests.

### M6 — Others build on Wepl (Phase 7 target)
*Claim:* an external tenant can provision accounts and move money via a public,
versioned, tenant-isolated API, receiving webhooks-out — with money still moving only
through `post_journal()`.
*Proof (target):* a sandbox integration runs against `FakeProvider` behind a tenant;
a live tenant's ledger reconciles independently.

### M7 — Regulated-grade infrastructure (Phase 8 target)
*Claim:* AML monitoring, treasury, and data residency are in place; a regulated
entity is comfortable placing members' money on Wepl.
*Proof (target):* AML monitoring hangs off the one money door; the case timeline and
audit log satisfy an external auditor; data residency pins a tenant to a
jurisdiction.

## The definition of done for the whole vision

Restating the roadmap's own bar ([Vision](../product/01-vision.md)): Wepl is a true
Financial OS when (a) the double-entry ledger is the only monetary truth; (b)
`post_journal()` is the sole money path carrying limits/risk/audit; (c) a global
trial balance is provably zero in CI and prod; (d) a new rail/currency ships without
touching financial logic; and (e) statements come straight from the GL. Claims
(a)–(e) are **reached at the core**; the remaining work is breadth (more rails,
currencies, products), depth (compliance, treasury), and exposure (BaaS).

## What "done (core)" means, honestly

Several phases are marked "Done (core)": the architectural spine exists and is
tested, but breadth work continues (more report types, more control policies, more
currencies exercised in production). The handbook states this honestly rather than
claiming completeness ([Charter](../00-charter.md)); "done (core)" means the *shape*
is settled and the *invariants* hold, not that every conceivable feature within the
phase is built.

## Definition of Done (per work item)

Every `P{phase}-{nn}` is done only when: **code merged · acceptance criteria met ·
tests green in CI · docs/ADR updated · checkbox ticked in both the phase doc and the
GitHub epic** ([Development Workflow](../engineering/34-development-workflow.md)).

---

*Continue to [Risks](62-risks.md) and [Future Evolution](63-future-evolution.md).*
