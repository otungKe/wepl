# The Wepl Handbook

> The living architectural handbook for Wepl — a ledger-first Financial Operating
> System for community finance. This is the constitution of the platform: not a
> tutorial, not a changelog, but the durable statement of **what we are building,
> why, and on what principles.** Everything else — code, roadmaps, tickets — is an
> implementation of what is written here.

---

## The reference baseline

**This repository — as documented by this handbook — is the reference starting point
for all future work on Wepl.** Everything that came before is prologue: the code is
now ledger-first, the architecture is written down, and the record (handbook + ADRs)
matches the code. From here, the platform moves forward by *convergence and addition*
([Convergence Plan](program/61-convergence-plan.md)), not by re-invention.

Two consequences for how we work from this baseline:

- **The past is in git and the ADRs, not in the code.** Source comments describe what
  the code does and *why it must be so* — never what changed, when, or by which
  PR/work-item/phase. A CI guard enforces this, so the codebase reads as a clean,
  timeless description of the system as it is now. (References to a governing
  *decision* — an `ADR-XXXX` — are welcome; those are durable rationale, not history.)
- **A new collaborator should be able to start here and be correct.** If any part of
  this handbook or the code would leave that person guessing, that is a defect to fix
  ([Charter](00-charter.md)). New engineers begin at [Getting Started](GETTING-STARTED.md).

---

## How to read this handbook

This is not one document. It is a set of cross-referenced documents, each owning
one topic, organised so that a new engineer joining years from now can understand
not only *what* we built but *why* we built it that way. Read it in the order
below the first time; use it as a reference thereafter.

The handbook is **descriptive of intent, not of the current commit.** Where the
code has caught up to the blueprint, the document says so. Where it has not, the
document states the target and points at the gap. When the two disagree, the
handbook is the position we are moving toward — and either the code is wrong or
the handbook is out of date, and one of them must be corrected. That tension is
the point: this is how the platform stays coherent.

### The relationship to ADRs and the roadmap

- **The handbook** states the enduring shape of the system — the constitution.
- **[ADRs](../adr/README.md)** are the immutable record of individual decisions —
  the case law. Each handbook chapter cites the ADRs that justify it. When a
  decision changes, a new ADR supersedes the old one and the affected handbook
  chapter is revised.
- **The [roadmap](../roadmap/README.md)** is the sequence of work that carries the
  code toward the blueprint — the legislative calendar.

If you only have five minutes, read the [Charter](00-charter.md), the
[Core Principles](product/03-principles.md), and the
[Financial Architecture](domain/12-financial-architecture.md). Those three carry
most of the platform's DNA.

---

## Table of contents

### 0. Foundations
- [Getting Started — Day 1](GETTING-STARTED.md) — **new here? start with this.** From clone to a correct first change.
- [00 — Charter](00-charter.md) — why we begin again; what this handbook is and is not.
- [01 — Glossary & Ubiquitous Language](01-glossary.md) — the shared vocabulary; the words mean exactly one thing.

### 1. Product
- [Product / 01 — Vision](product/01-vision.md) — where Wepl is going and what winning looks like.
- [Product / 02 — Philosophy](product/02-philosophy.md) — the beliefs about people and money that shape every decision.
- [Product / 03 — Core Principles](product/03-principles.md) — the non-negotiable rules, product and engineering.
- [Product / 04 — Business Model](product/04-business-model.md) — how Wepl creates and captures value.
- [Product / 05 — User Journeys](product/05-user-journeys.md) — the canonical flows, end to end.
- [Product / 06 — UX Philosophy & Design System](product/06-ux-and-design.md) — how the product should feel, and the system that makes it consistent.

### 2. Domain
- [Domain / 10 — Domain Model](domain/10-domain-model.md) — the aggregates, invariants, and boundaries of the business.
- [Domain / 12 — Financial Architecture](domain/12-financial-architecture.md) — the ledger, the money door, the chart of accounts. **The heart of the system.**
- [Domain / 13 — Governance Architecture](domain/13-governance-architecture.md) — how communities decide and act collectively.
- [Domain / 14 — Identity Architecture](domain/14-identity-architecture.md) — customers, staff, KYC, and identity-as-a-ledger.

### 3. Architecture
- [Architecture / 20 — System Architecture](architecture/20-system-architecture.md) — the runtime shape: services, data stores, message flow.
- [Architecture / 21 — Technology Stack](architecture/21-technology-stack.md) — every chosen technology and the reason it was chosen.
- [Architecture / 22 — Module Boundaries](architecture/22-module-boundaries.md) — the apps, their contracts, and the dependency rules between them.
- [Architecture / 23 — API Architecture](architecture/23-api-architecture.md) — conventions, versioning, the public BaaS surface.
- [Architecture / 24 — Data Architecture](architecture/24-data-architecture.md) — storage, projections, migrations, retention, residency.
- [Architecture / 25 — Security Architecture](architecture/25-security-architecture.md) — the threat model and the defences.
- [Architecture / 26 — Eventing Architecture](architecture/26-eventing-architecture.md) — the transactional outbox and durable domain events.
- [Architecture / 27 — Payments Architecture](architecture/27-payments-architecture.md) — the rail port/adapter and settlement.

### 4. Engineering
- [Engineering / 30 — Engineering Principles](engineering/30-engineering-principles.md) — how we build, and what we refuse to do.
- [Engineering / 31 — Coding Standards](engineering/31-coding-standards.md) — the conventions that make the code one voice.
- [Engineering / 32 — Folder Structure](engineering/32-folder-structure.md) — where things live and why.
- [Engineering / 33 — Testing Strategy](engineering/33-testing-strategy.md) — what we test, how, and the gates that must stay green.
- [Engineering / 34 — Development Workflow](engineering/34-development-workflow.md) — from idea to merged, deployed change.
- [Engineering / 35 — Documentation Standards](engineering/35-documentation-standards.md) — how this handbook stays alive.

### 5. Frontend & Mobile
- [Frontend / 40 — Frontend Architecture](frontend/40-frontend-architecture.md) — the customer web app and the ops console.
- [Frontend / 41 — Mobile Architecture](frontend/41-mobile-architecture.md) — the Expo/React Native client.

### 6. Operations
- [Operations / 50 — Infrastructure](operations/50-infrastructure.md) — where the platform runs.
- [Operations / 51 — Deployment Strategy](operations/51-deployment-strategy.md) — how change reaches production safely.
- [Operations / 52 — Observability](operations/52-observability.md) — how we know what the system is doing.
- [Operations / 53 — Operational & Scalability Strategy](operations/53-operations-and-scalability.md) — running it, and growing it.

### 7. Program
- [Program / 60 — Roadmap & Milestones](program/60-roadmap-and-milestones.md) — the arc from here to a Financial OS.
- [Program / 61 — Convergence Plan](program/61-convergence-plan.md) — **where we start now:** moving the existing code onto the blueprint (evolve + clean, not rewrite).
- [Program / 62 — Risks](program/62-risks.md) — what could break the platform, and the mitigations.
- [Program / 63 — Future Evolution](program/63-future-evolution.md) — the ten-year view.
- [Program / 64 — Decision Log](program/64-decision-log.md) — the ADR index, annotated.

---

## The three sentences

If this entire handbook were lost and only three sentences survived, these would
be enough to rebuild it in spirit:

1. **The double-entry ledger is the single source of monetary truth, and
   `post_journal()` is the only door money walks through.**
2. **Every source of truth that can be immutable and derived is immutable and
   derived — money, identity, audit, governance — and mutable projections are
   caches we can throw away and rebuild.**
3. **Wepl serves communities that manage money together; the software's job is to
   make that trustworthy, legible, and effortless, and to disappear.**

---

## Status of the handbook

| Section | State |
|---------|-------|
| Foundations | Drafted |
| Product | Drafted |
| Domain | Drafted |
| Architecture | Drafted |
| Engineering | Drafted |
| Frontend & Mobile | Drafted |
| Operations | Drafted |
| Program | Drafted |

"Drafted" means the chapter exists and is internally consistent with the current
codebase and ADR corpus. Chapters are revised whenever a superseding ADR lands.
See [Documentation Standards](engineering/35-documentation-standards.md) for how
this table is kept honest.
