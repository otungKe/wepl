# 01 — Glossary & Ubiquitous Language

> One word, one meaning. This glossary is the shared vocabulary of Wepl. When code,
> API, UI, and conversation all use the same word for the same thing, whole classes
> of misunderstanding disappear. If a term here is ambiguous in use, that is a
> defect to fix — either rename the code or sharpen the definition.

The domain language is enforced, not merely suggested: model classes, service
functions, event names, and API fields should read as this glossary reads. See
[Coding Standards](engineering/31-coding-standards.md) for how naming is policed.

---

## Money & ledger

**Ledger** — The double-entry book of record in `apps/ledger/`. The *single*
source of monetary truth. Not a log, not a report — the book itself.

**`post_journal()`** — The one function through which money moves
(`apps/ledger/posting.py`). Guarantees Σdebit == Σcredit (≥2 lines), idempotency
on `idempotency_key`, and a consistent balance projection. "The money door."

**Journal Entry** — One atomic, immutable financial event: a set of balanced
lines posted together. Once written, never mutated; corrected only by a reversing
entry.

**Journal Line** — One debit or one credit against one account, belonging to a
journal entry. The immutable atom of the ledger.

**Account** — A node in the [Chart of Accounts](#chart-of-accounts-coa). Either a
canonical GL account (e.g. `1000` M-Pesa Float) or a lazily created member
sub-ledger. Identity is `id`/`account_uid`; the human-readable `code` is display
metadata (ADR-0025).

**Sub-ledger account** — A per-member, per-fund account (e.g. member liability in
a contribution) that rolls up into a GL "head." Created on first use.

**Chart of Accounts (COA)** — The catalogue of accounts and the rules that resolve
a logical account to a row (`apps/ledger/coa.py`). Anchored, sortable, GL-headed
codes (ADR-0025).

**Account Balance** — A *derived projection* of an account's balance
(`apps/ledger/balances.py`), rebuildable by replaying journal lines. A cache, never
truth.

**Posting map** — The catalogue of canonical debit/credit recipes
(`apps/ledger/posting_map.py`). Every money operation names a recipe here that
returns balanced `list[Line]`; services never hand-roll journals.

**Money** — The value object for monetary amounts (`apps/ledger/money.py`):
`Decimal` + currency, never float (ADR-0003). Precision is `Decimal(20,4)`.

**Trial balance** — The sum of all debits minus all credits across the ledger.
**Provably zero** at all times; verified in CI and by `reconcile_ledger`.

**Financial Transaction** — A member-facing, human-legible grouping over one or
more journal entries — the unit a person recognises as "a payment" (`apps/ledger`,
ADR-0025). Carries the searchable reference and counterparty name.

**Pool** — A fund's control account, treated as a first-class account so that
fund-level movements are addressable in the same namespace as everything else
(ADR-0025).

---

## Community finance products

**Community** — The top-level social and financial container: a group of members
who manage money together. Owns membership, roles, and governance
(`apps/communities`).

**Member** — A `users.User` in the context of a community. Identified platform-wide
by **phone number** and by a stable **member number**.

**Contribution** — A collective savings/collection product: members pay into a
shared fund on a schedule (`apps/contributions`). The most general money-pooling
primitive.

**ROSCA / Rotating payout** — A rotating savings-and-credit arrangement: members
contribute each cycle and the pooled amount is paid out to one member per cycle in
turn.

**Welfare fund** — A mutual-aid pool members draw on for defined events (bereavement,
emergencies) under community rules.

**Shares fund** — An equity-like pool where members hold proportional stakes in a
common pot.

**Emergency advance** — A short-term advance to a member against the fund, tracked
as a receivable (`1200` Advances Receivable) and optionally bearing interest
(`4100` Interest Income).

**Standing order** — A member's instruction to contribute automatically on a
schedule.

**Fee** — Platform revenue on a money movement, posted to `4000` Fee Revenue.
Fees, excise duty, and withholding have canonical postings (ADR-0024).

---

## Governance

**Role** — A member's authority within a community (e.g. admin vs member). Governs
what actions are permitted.

**Proposal / Vote** — The mechanism by which a community makes a collective
decision that gates a privileged action (e.g. a payout). Subject to a configurable
**voting threshold** (admins-only, 25/50/100%).

**Quorum** — The minimum participation for a vote to be binding.

**Governance action** — A privileged operation that a governance decision unlocks.
Authorisation is centralised (ADR-0009), not scattered per-view.

---

## Identity & access

**User** — A customer identity (`users.User`). **Phone number is the identifier**;
there is no username. Auth is phone + OTP, JWT via SimpleJWT.

**KYC Profile / Tier** — A user's verification standing. Tier-0 → Tier-1 gate runs
through the identity provider port (ADR-0022, ADR-0023). `KYCProfile.status` is a
*projection* of the verification case.

**Verification Case** — The identity analogue of a journal entry
(`apps/verification`): every KYC journey is a case whose immutable `CaseEvent`
timeline is the source of truth. Decisions go through `verification.service.decide()`.

**Case Event** — An immutable entry in a verification case's timeline. Identity's
"journal line."

**Case Document** — A versioned KYC document pinned to its storage object. A
re-submission adds a version; it never overwrites prior evidence.

**Staff Account** — A back-office operator (`apps/backoffice`): corporate **email +
password**, admin-provisioned. A *separate identity from customers*. Authenticates
with a dedicated staff JWT (`type: "ops"`).

**Capability** — A code-defined unit of operator authority (`capabilities.py`) over
`ops:*` Django Groups, enforced by `RequireCapability`. RBAC for staff.

**Audit Event** — An append-only record of an operator action (`record_action()`,
ADR-0019). Every ops action writes one.

**OTP bypass** — `STAGING_OTP_BYPASS`: accepts a fixed `000000` OTP in dev/staging.
Production **refuses to boot** if it is set while `DEBUG=False` (an intentional
guard, never to be weakened).

---

## Events & delivery

**Domain event** — A business fact worth announcing (e.g. "contribution paid").
Emitted via `emit(...)` (`apps/core/events.py`) as an **Outbox Event** row written
*in the current transaction*.

**Outbox Event** — The durable row that guarantees a domain event is never lost: a
rolled-back transaction discards it; a crash never drops it (ADR-0006).

**Outbox relay** — `process_outbox` (`apps/core/tasks.py`): delivers events
at-least-once by re-firing the `domain_event` signal. Consumers dedupe on
`Notification.event_id`.

**Notification** — A delivered message to a user across one or more channels
(ADR-0015). Idempotent on `event_id`.

---

## Payments

**Payment provider / rail** — A settlement network behind the `PaymentProvider`
port (`apps/payments/providers/`). M-Pesa is adapter #1; `FakeProvider` backs tests
(ADR-0005).

**Daraja** — Safaricom's M-Pesa API. All Daraja wire details (STK push, B2C,
callback fields) stay inside `apps/payments/providers/mpesa.py` and `apps/mpesa/`.
Code above the port never sees Daraja field names.

**Normalized result** — `CollectionResult` / `PayoutResult` / `CallbackEvent` /
`StatusResult`: the rail-agnostic vocabulary above the provider port.

**Collection** — Money in (e.g. STK push to a member's phone).

**Payout / B2C** — Money out (business-to-customer disbursement).

---

## Platform & tenancy

**Financial OS** — The end-state Wepl: a ledger-first platform where any money
product, rail, or currency plugs into one posting chokepoint. See
[Vision](product/01-vision.md).

**Tenant** — An isolated boundary of data and configuration
(`apps/tenants`, ADR-0008). The unit of multi-tenancy that enables BaaS.

**BaaS (Banking-as-a-Service)** — The eventual public product: external parties
build on Wepl's ledger via a public API, webhooks-out, sandbox, and API keys
(roadmap Phase 7).

**Ops console** — The back-office application at `/api/ops/*` used by staff. A
*separate deployment* from the customer app; never co-hosted.

---

## Work-item vocabulary

**Phase** — A roadmap epic (`P{phase}`), e.g. Phase 0 = Ledger-First Cutover.

**Work item** — `P{phase}-{nn}` (e.g. `P0-05`): a stable ID referenced in commits,
phase docs, and issues.

**ADR** — Architecture Decision Record: an immutable record of one decision
(`docs/adr/`).

---

*Continue to [Product / Vision](product/01-vision.md).*
