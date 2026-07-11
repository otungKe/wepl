# Architecture / 22 — Module Boundaries

> The apps, what each one owns, and the dependency rules between them. Wepl is a
> **modular monolith**: one deployable, many strictly-bounded modules. This chapter
> defines the seams — the contracts modules expose and the arrows they are allowed
> to draw — so the monolith stays modular and could be split later along real
> boundaries rather than torn along arbitrary ones.

---

## Why a modular monolith

The domain's defining operation is *money-and-its-event committed in one atomic
transaction* ([System Architecture](20-system-architecture.md)). A premature
microservices split would turn that local transaction into a distributed one —
trading a solved problem (ACID in Postgres) for an unsolved one (distributed
consensus) with no product benefit. So Wepl is **one process, many modules**, with
discipline enforced by boundaries rather than by network calls. The modules are
drawn so that *if* we ever extract a service, the seam already exists.

## The modules

Each `apps/*` module owns a slice of the domain. "Owns" means: it defines the
models, it is the only module that mutates them, and other modules reach it through
its documented surface (service functions, ports, events) — never by reaching into
its internals.

### Core / platform layer (depended upon by everyone)
| Module | Owns | Surface it exposes |
|--------|------|--------------------|
| `ledger` | The book of record: accounts, journals, balances, money, COA, posting map, reporting, FX, controls hooks | `post_journal()`, COA resolvers, `Money`, reporting queries |
| `core` | The event bus + transactional outbox; shared exceptions | `emit()`, `process_outbox`, `TransitionError` |
| `tenants` | The multi-tenant isolation boundary | tenant context/scoping |
| `audit` | The append-only operator audit log | `record_action()` |

### Rails & delivery layer
| Module | Owns | Surface |
|--------|------|---------|
| `payments` | The `PaymentProvider` port + provider registry; payment aggregate/reconciliation | port interface, normalized results |
| `mpesa` | Daraja wire details (STK, B2C, callbacks) — the M-Pesa adapter's guts | (internal; reached only via the payments port) |
| `notifications` | Multi-channel delivery (SMS/email/push) | notification consumers, delivery API |
| `files` | Media/document storage pipeline | storage-pinned document objects |
| `search` | Search indexing/query | search API |

### Identity layer
| Module | Owns | Surface |
|--------|------|---------|
| `users` | Customer identity: phone auth, OTP, sessions, KYC tiers, identity provider port, OCR | auth views, tier gates, `IdentityVerificationProvider` port |
| `verification` | Identity-as-a-ledger: `VerificationCase`, `CaseEvent`, `CaseDocument` | `verification.service.decide()` |
| `backoffice` | Staff identity + ops console: `StaffAccount`, capabilities, staff JWT | `/api/ops/*`, `RequireCapability` |

### Product / community layer
| Module | Owns | Surface |
|--------|------|---------|
| `communities` | Communities, membership, roles, ownership/lifecycle, governance | membership + governance policy |
| `contributions` | The money products: contributions, welfare, shares, advances, standing orders | product services that *call* the ledger |
| `controls` | Limits & risk at the posting chokepoint | control checks, `ControlOverride` |
| `conversations` | Group chat (Channels-backed) | chat API/consumers |
| `activity` | Activity feeds | feed consumers/queries |
| `reminders` | Scheduled member reminders | reminder tasks |

## The dependency rules (the constitution of the code)

These rules are what keep the monolith modular. They are the structural expression
of the [Domain Model's dependency rule](../domain/10-domain-model.md).

### Rule 1 — The ledger depends on nothing above it
`ledger` must not import from `contributions`, `communities`, `payments`, or any
product module. It knows about accounts and journals, not about "welfare" or
"M-Pesa." Everything money-related depends on `ledger`; `ledger` depends only on
`core`/framework. *This is the most important rule; violating it re-couples the
whole system to the products of the moment.*

### Rule 2 — Products depend on the ledger, never the reverse
`contributions`, `communities`, and friends call `post_journal()` and COA
resolvers. A change to a product's rules must never require editing `ledger`. If it
seems to, the abstraction is wrong.

### Rule 3 — Provider guts stay behind their port
`mpesa` (Daraja) is reachable only through the `payments` port (**P-18**). No module
above the port imports Daraja field names. The same holds for the identity provider
port (`users/identity/`) and the notification channels. Adapters point *inward* at
the port; the port never points out at an adapter.

### Rule 4 — Cross-module communication of *facts* goes through events
When something happens in module A that module B cares about, A `emit()`s a domain
event and B consumes it (registered in B's `AppConfig.ready()`), rather than A
calling into B directly. This keeps modules decoupled and delivery durable
(**P-9**). Payloads are JSON-serialisable primitives (IDs/strings/numbers), never
ORM objects — so an event never smuggles a module's internal model across a
boundary.

### Rule 5 — Identity and money state change only through their one door
No module mutates ledger rows except via `post_journal()`; no module mutates
verification/KYC state except via `verification.service.decide()`; no module writes
audit rows except via `record_action()`. Doors, not back doors (**P-2/P-10/P-14**).

### Rule 6 — Everything is tenant-scoped
New models and queries respect the tenant boundary (`tenants`, **P-19**). Tenancy is
a cross-cutting rule, not a module you can ignore.

## How the rules are (and should be) enforced

- **CI grep-guards** already forbid the biggest violations of Rule 1/Rule 5 —
  reintroducing `LedgerEntry`, mutable balance caches, or bypassing the money door
  ([Principle P-22](../product/03-principles.md)).
- **The port pattern** structurally enforces Rule 3: there is simply no import path
  to Daraja above the port.
- **Review** enforces the rest, citing the rule number. A tool that statically
  checks import boundaries (an `import-linter`-style contract) is a natural future
  addition and is noted in [Future Evolution](../program/63-future-evolution.md).

## God-module hazard (a known, named risk)

The audit flagged `contributions/services.py` (~2,000 lines) and `models.py` (~850)
as god modules. The boundary discipline above is the *cure*, applied internally:
`contributions` already splits into a `services/` package and `views/` package
([ADR-0013](../../adr/0013-contributions-module-split.md)). The rule is that a
module's *internal* size is managed by splitting along sub-domain seams (welfare vs
shares vs advances vs contributions) — **not** by leaking logic into other modules
or, worse, into the ledger.

## Where a future service split would cut

If Wepl ever outgrows the monolith, the seams are already drawn:

1. **The ledger** could become a ledger service (it depends on nothing above it —
   Rule 1 makes this the cleanest cut).
2. **The ops/backoffice plane** is already a separate deployment on the frontend
   and a bounded backend module — a natural extraction.
3. **Tenant sharding** (Phase 7 BaaS) is a horizontal split along the tenant
   boundary, not a functional one.

We do **not** split now; we keep the seams clean so we *could*.

---

*Continue to [API Architecture](23-api-architecture.md) and
[Data Architecture](24-data-architecture.md).*
