# Domain / 10 — Domain Model

> The business, modelled: the aggregates, the invariants that make each one
> trustworthy, and the boundaries between them. This chapter is the map; the
> [Financial](12-financial-architecture.md), [Governance](13-governance-architecture.md),
> and [Identity](14-identity-architecture.md) chapters are the territory in detail.

Vocabulary here is the [Glossary](../01-glossary.md); module homes are in
[Module Boundaries](../architecture/22-module-boundaries.md).

---

## The domain in one paragraph

People form **communities** to manage money together. Inside a community they run
one or more **funds** — contributions, welfare, shares, advances — each a way of
pooling and moving money under agreed rules. Money moves on real **payment rails**
and is recorded, without exception, in the **ledger**. Privileged actions (notably
payouts) are unlocked by **governance**. Who a person *is* — for the purpose of
being trusted with money — is established by **identity/KYC**. Everything a person
reads is a projection of immutable truth; everything an operator does is audited.

## The aggregates and their invariants

An *aggregate* is a cluster of objects with a consistency boundary and one rule
that must always hold. Naming them explicitly keeps the model honest.

### Ledger (the book of record) — `apps/ledger`
- **Aggregate root:** `JournalEntry` (grouped for humans by `FinancialTransaction`).
- **Invariant:** every entry balances (Σdebit == Σcredit, ≥2 lines) and is
  immutable; the global trial balance is zero.
- **Why it's the center:** every other aggregate that touches money *reads from* or
  *posts to* this one, and never keeps its own authoritative money number.
- Detail: [Financial Architecture](12-financial-architecture.md).

### Community — `apps/communities`
- **Aggregate root:** `Community`, owning `CommunityMembership`.
- **Invariants:** a community always has a clear owner and lifecycle state
  (ADR-0011); membership has explicit status and a stable member number; role
  determines governance power.
- **Boundary:** owns *who is in the group and what they may do*; does **not** own
  money (that's the ledger) or identity verification (that's KYC).

### Funds (contributions, welfare, shares, advances) — `apps/contributions`
- **Aggregate roots:** `Contribution`, `WelfareFund`, `SharesFund`, and advance
  records. All live in one app because they are variations on one idea — a pool with
  rules — and split internally rather than across app boundaries (ADR-0013).
- **Invariants:** a fund's *state machine* (open/closed, cycle, schedule) is
  explicit and uses optimistic locking (`UPDATE ... WHERE state = current`); a
  fund's *balance is derived from the ledger*, never stored as a mutable counter
  (**P-3**). The fund owns *rules and schedule*; the ledger owns *the money*.
- **Boundary:** a fund decides *when and how much* should move; `post_journal()`
  decides *that it moved and stays balanced*. The fund never writes journals by
  hand — it names a recipe (**P-5**).

### Governance — `apps/communities` (+ centralized policy)
- **Aggregate:** proposals/votes over privileged community actions.
- **Invariant:** a privileged action (e.g. a payout) cannot execute unless the
  configured threshold/quorum is met; authorization is centralized (ADR-0009), not
  re-decided per view.
- Detail: [Governance Architecture](13-governance-architecture.md).

### Identity / KYC — `apps/users`, `apps/verification`
- **Aggregate root:** `VerificationCase`, with an immutable `CaseEvent` timeline
  and versioned `CaseDocument`s.
- **Invariant:** identity state changes only through
  `verification.service.decide()`, which enforces a transition table; `KYCProfile`
  status is a projection; evidence is versioned, never overwritten (**P-10/P-11**).
- Detail: [Identity Architecture](14-identity-architecture.md).

### Payments — `apps/payments`, `apps/mpesa`
- **Aggregate:** the payment attempt/result, reconciled against rail callbacks
  (ADR-0014).
- **Invariant:** rail-specific detail stays behind the `PaymentProvider` port
  (**P-18**); a payment result is normalized before any core code sees it; posting
  to the ledger is idempotent against duplicate callbacks.
- Detail: [Payments Architecture](../architecture/27-payments-architecture.md).

### Eventing — `apps/core`
- **Aggregate:** `OutboxEvent`.
- **Invariant:** an event is written in the emitting business transaction and
  delivered at-least-once; consumers dedupe (**P-9**).
- Detail: [Eventing Architecture](../architecture/26-eventing-architecture.md).

### Audit — `apps/audit`
- **Aggregate:** `AuditEvent` (append-only).
- **Invariant:** every operator action produces one; it is never mutated or deleted
  (**P-14**, ADR-0019).

### Supporting contexts
`apps/notifications` (multi-channel delivery, ADR-0015), `apps/activity` (feeds,
ADR-0016), `apps/conversations` (chat, ADR-0012), `apps/reminders`, `apps/files`
(media pipeline, ADR-0018), `apps/search` (ADR-0017), `apps/controls` (limits/risk,
ADR-0007), `apps/tenants` (isolation, ADR-0008), `apps/backoffice` (ops console).
These orbit the core aggregates and are detailed in
[Module Boundaries](../architecture/22-module-boundaries.md).

## The dependency rule (which way arrows point)

The single most important structural fact in the domain:

```
      funds ─┐        governance ─┐
             ├─► LEDGER ◄─────────┤
   payments ─┘        controls ───┘
             (everyone posts to / reads from the ledger;
              the ledger depends on nothing above it)
```

- **The ledger depends on nothing.** It knows nothing of contributions, welfare, or
  M-Pesa. It offers `post_journal()` and account resolution; that is all.
- **Products, payments, governance, and controls depend on the ledger**, never the
  reverse. A change to a fund's rules cannot require a change to the ledger.
- **Provider details point *inward* through ports.** M-Pesa depends on the payment
  port's shape; the port does not depend on M-Pesa (**P-18**).

This is the Dependency Inversion Principle applied at the domain scale, and it is
what makes the [Vision](../product/01-vision.md)'s "add a product/rail/currency
without touching financial logic" achievable rather than aspirational.

## Cross-cutting truths (the recurring pattern)

Four aggregates independently implement the same idea — **immutable log + disposable
projection** ([Philosophy §3](../product/02-philosophy.md)):

| Aggregate | Immutable truth | Disposable projection |
|-----------|-----------------|-----------------------|
| Ledger | `JournalLine` | `AccountBalance` |
| Identity | `CaseEvent` | `KYCProfile.status` |
| Audit | `AuditEvent` | (ops read models) |
| Eventing | `OutboxEvent` | delivery/notification state |

When you add a new aggregate that holds important truth, use this table as a
checklist: *what is my immutable log, and what is my rebuildable projection?* If you
cannot answer, the design is not finished.

## Consistency & transactions

- **Money and its event are one transaction.** `post_journal()` and the `emit()`
  that announces it commit together, so a rolled-back payment cannot leak a "payment
  succeeded" event (**P-9**).
- **State machines use optimistic locking**, so two concurrent actors cannot both
  win a transition.
- **Idempotency keys** guard every money path against retries and duplicate
  callbacks.
- **Eventual consistency is confined to projections and delivery** — never to the
  book of record. Balances *derive* synchronously in the posting transaction; feeds
  and notifications catch up asynchronously via the outbox.

## Multi-tenancy (the outer boundary)

Every aggregate above is (or is being made) **tenant-scoped** (ADR-0008,
`apps/tenants`, **P-19**). A tenant is the isolation boundary that later lets a
third party run their own communities/funds/ledger on Wepl (BaaS, Phase 7). Tenancy
is modelled as a boundary threaded through the domain, not a `tenant_id` bolted on
at the end.

---

*Continue to [Financial Architecture](12-financial-architecture.md) (the center),
then [Governance](13-governance-architecture.md) and
[Identity](14-identity-architecture.md).*
