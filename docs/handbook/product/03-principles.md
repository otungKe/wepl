# Product / 03 — Core Principles

> The non-negotiable rules of the platform, stated so plainly that a reviewer can
> cite them by number. Where [Philosophy](02-philosophy.md) is the *why*, this is
> the *law*. A change that violates a P-rule needs an ADR that changes the rule
> first — not an exception in a pull request.

Each principle is numbered (`P-n`), stated as a rule, given its rationale in one
line, and linked to where it is enforced.

---

## Money & ledger

### P-1 — One book of record
The double-entry ledger is the single source of monetary truth. No other store may
be treated as authoritative for money.
*Why:* two truths for money guarantees drift.
*Enforced by:* [ADR-0001](../../adr/0001-ledger-first-double-entry.md); CI grep-guard.

### P-2 — One money door
All value movement goes through `post_journal()`. Creating `JournalEntry`/
`JournalLine` rows any other way is forbidden.
*Why:* one insertion point for every cross-cutting concern.
*Enforced by:* [ADR-0004](../../adr/0004-post-journal-single-entrypoint.md); CI.

### P-3 — Balances are derived, never stored as mutable counters
Balances come from immutable journal lines via a rebuildable projection. Any
surviving balance column is an explicitly labelled cache.
*Why:* mutable counters are un-provable and drift.
*Enforced by:* [ADR-0002](../../adr/0002-remove-legacy-ledger-and-mutable-balances.md);
CI fails on `current_amount = F(...)`-style caches.

### P-4 — Money is `Money`/`Decimal`, never float
Monetary amounts are `Decimal(20,4)` inside the `Money` value object, currency
attached.
*Why:* float silently loses money.
*Enforced by:* [ADR-0003](../../adr/0003-money-representation.md); `apps/ledger/money.py`.

### P-5 — Never hand-roll a journal
Every money operation names a canonical recipe in `posting_map.py`; services call
builders, they do not assemble debits and credits inline.
*Why:* the recipe is the reviewed, tested accounting truth.
*Enforced by:* `apps/ledger/posting_map.py`; review.

### P-6 — The trial balance is provably zero, always
Σdebit == Σcredit globally, checked in CI and by `reconcile_ledger`, and re-checked
at COMMIT by a deferred DB constraint trigger.
*Why:* conservation of money must be demonstrable, not assumed.
*Enforced by:* DB trigger; `reconcile_ledger`; CI.

### P-7 — Additive before destructive
New money paths are built, dual-written, and verified green before old paths are
deleted.
*Why:* you cannot safely delete working money code on faith.
*Enforced by:* roadmap discipline; review.

---

## Truth, events & identity

### P-8 — Immutable log, disposable projection
Anything holding important truth (money, identity, audit, events) is an append-only
immutable sequence with a rebuildable projection for reads.
*Why:* immutable truth cannot be silently corrupted; projections are cheap to
rebuild.
*Enforced by:* ledger, `apps/verification`, `apps/audit`, `apps/core` outbox.

### P-9 — Durable events, never lost
Domain events are written as `OutboxEvent` rows in the emitting transaction and
delivered at-least-once; consumers dedupe idempotently.
*Why:* a rolled-back transaction must discard its event; a crash must never drop
one.
*Enforced by:* [ADR-0006](../../adr/0006-transactional-outbox.md); `emit()`,
`process_outbox`.

### P-10 — Identity changes go through one service
All KYC/case decisions flow through `verification.service.decide()`, which enforces
the transition table and appends an immutable `CaseEvent`. `KYCProfile.status` is a
projection.
*Why:* identity is a ledger too; its truth must be as disciplined as money's.
*Enforced by:* `apps/verification`; ADR-0022/0023.

### P-11 — Evidence is versioned, never overwritten
A re-submitted KYC document adds a version pinned to a new storage object; it never
overwrites the evidence a prior decision was made against.
*Why:* decisions must remain auditable against the exact evidence they used.
*Enforced by:* `CaseDocument` versioning.

---

## Access, security & operations

### P-12 — Two separate identities: customers and staff
Customers are `users.User` (phone + OTP, customer JWT). Operators are `StaffAccount`
(email + password, `type:"ops"` JWT). They never share an identity, a token, or a
deployment.
*Why:* mixing customer and operator authority is a catastrophic blast radius.
*Enforced by:* `apps/backoffice`; separate JWTs; separate frontends.

### P-13 — Authorisation is centralised
Money permissions run through `FinancialPermissions`; operator permissions through
the capability map and `RequireCapability`. Authorisation is not re-implemented
per view.
*Why:* scattered authz is authz that will eventually be forgotten somewhere.
*Enforced by:* [ADR-0009](../../adr/0009-centralized-authorization-policy.md).

### P-14 — Every operator action is audited
Every `/api/ops/*` action writes an append-only `AuditEvent` via `record_action()`.
*Why:* operator power over customer money demands a non-repudiable trail.
*Enforced by:* [ADR-0019](../../adr/0019-append-only-audit-log.md).

### P-15 — The production OTP-bypass guard is sacred
Production refuses to boot if `STAGING_OTP_BYPASS` is set while `DEBUG=False`. This
guard is never weakened.
*Why:* a fixed `000000` OTP in production is a total auth bypass.
*Enforced by:* `config/settings/production.py` (`ImproperlyConfigured` at boot).

### P-16 — Degrade cleanly and honestly
When a dependency (cache, broker, Channels) is unavailable, the system fails in a
defined, honest way — a truthful `503`, a documented fail-open/fail-closed choice —
never a silent lie or an opaque 500.
*Why:* dishonest failure converts a recoverable outage into a trust breach.
*Enforced by:* request-path hardening (commits #155–#157); review.

---

## Platform shape

### P-17 — Rails and currencies are pluggable; financial logic is not touched to add them
A new payment rail is a new adapter behind the `PaymentProvider` port; a new
currency is data. Neither edits money logic.
*Why:* the whole point of a Financial OS is that the core is stable while the edges
multiply.
*Enforced by:* [ADR-0005](../../adr/0005-payment-provider-abstraction.md);
[ADR-0003](../../adr/0003-money-representation.md); Phase 1/5.

### P-18 — Provider details stay behind the port
Daraja/M-Pesa wire vocabulary lives only in `apps/payments/providers/mpesa.py` and
`apps/mpesa/`. Code above the port speaks only normalized results.
*Why:* leaking a provider's field names into core logic re-couples the whole system
to one rail.
*Enforced by:* ADR-0005; review.

### P-19 — Tenancy is a boundary, not a column afterthought
Multi-tenant isolation is a first-class boundary (`apps/tenants`), threaded through
new code from the start even before BaaS ships.
*Why:* retrofitting isolation onto a single-tenant core is a rewrite.
*Enforced by:* [ADR-0008](../../adr/0008-multi-tenancy.md).

---

## Engineering conduct

### P-20 — Decisions are recorded
Anything structural gets an ADR before it is built; the [handbook](../README.md) is
revised when the ADR lands.
*Why:* undocumented decisions are re-litigated forever.
*Enforced by:* [ADR process](../../adr/README.md); review.

### P-21 — The core stays boring
The financial core uses mature, well-understood technology and patterns; novelty is
spent only on genuine product differentiation.
*Why:* cleverness in the core is a tax on every future engineer.
*Enforced by:* [Engineering Principles](../engineering/30-engineering-principles.md).

### P-22 — Green gates are not optional
The money-core coverage floor (≥90%), the migration-drift check, the trial-balance
check, and the grep-guards are merge-blocking. A red gate is never merged around.
*Why:* the gates encode the principles; disabling a gate silently repeals a
principle.
*Enforced by:* `.github/workflows/ci.yml`.

---

## Using these principles

- In review, cite the rule: "This violates **P-2** — route it through
  `post_journal()`."
- To *change* a rule, write an ADR that supersedes the cited one, then revise this
  chapter and the [Decision Log](../program/64-decision-log.md).
- If you find code that violates a P-rule, that is a defect (per the
  [Charter](../00-charter.md)), not a precedent.

---

*Continue to [Business Model](04-business-model.md).*
