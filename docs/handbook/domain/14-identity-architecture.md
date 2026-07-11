# Domain / 14 — Identity Architecture

> Who a person *is*, for the purpose of being trusted with money — and how Wepl
> keeps two entirely separate identities: **customers** who own the money and
> **staff** who operate the platform. Identity in Wepl is modelled with the same
> discipline as money: **identity is a ledger too.**

Grounded in [ADR-0022](../../adr/0022-two-tier-access-model.md),
[ADR-0023](../../adr/0023-identity-verification-provider.md),
[ADR-0010](../../adr/0010-session-registry-and-token-revocation.md),
[ADR-0019](../../adr/0019-append-only-audit-log.md); realised in `apps/users`,
`apps/verification`, and `apps/backoffice`.

---

## Two populations, never one

The most important rule in this chapter, and one of the platform's sharpest
security decisions (**P-12**):

> **Customers and staff are separate identities, with separate credentials,
> separate tokens, and separate deployments. They never mix.**

| | Customer | Staff / operator |
|---|----------|------------------|
| Model | `users.User` | `StaffAccount` (`apps/backoffice`) |
| Identifier | **phone number** (no username) | corporate **email** |
| Credential | **OTP** (phone) → JWT | **password** (admin-provisioned) → JWT |
| Token type | customer SimpleJWT | staff JWT, `type: "ops"` |
| Provisioning | self-serve | admin-provisioned, `must_change_password`, **no self-serve reset** |
| Frontend | member app (mobile/web) | ops console (separate deployment) |
| Powers | own money, own group | operate the platform under capabilities |

Why so strict? Because an operator has power over *other people's* money. If a
customer identity could ever be escalated into an operator identity — shared token
format, shared login, co-hosted app — the blast radius would be catastrophic. The
separation is structural so the escalation path does not exist.

---

## Part A — Customer identity

### Phone-first auth
`phone_number` is the identifier; there is no username. Authentication is phone +
OTP, issuing a SimpleJWT. This fits the market (everyone has a phone and an M-Pesa
number) and keeps onboarding to seconds.

### The OTP-bypass guard (sacred)
`STAGING_OTP_BYPASS` accepts a fixed `000000` OTP for any phone in dev/staging so
tests and demos are frictionless. In production this is a **total auth bypass**, so
`config/settings/production.py` raises `ImproperlyConfigured` at boot if it is set
while `DEBUG=False`. **P-15**: this guard is never weakened. It is the difference
between a convenience and a catastrophe, decided once, enforced at boot.

### Sessions and revocation (ADR-0010)
A session registry backs token revocation, so a lost device or a compromised token
can be *revoked* rather than merely left to expire. Auth degrades honestly under a
cache outage (**P-16**): OTP verification returns an honest `503` rather than
silently passing, and the PIN path's lockout fails *open* by an explicit,
documented choice rather than locking every user out on a Redis blip (commits
#155–#157). Degradation behaviour is a *decision*, recorded, not an accident.

### KYC tiers (ADR-0022)
Customers exist at a **tier**. Tier-0 (phone-verified) can do little with money;
the **Tier-0 → Tier-1 gate** unlocks money movement and runs a real identity check.
Tiers are the throttle that lets onboarding be frictionless while money movement is
gated on verification — you can *join* in seconds but must be *verified* to
transact.

### Identity verification is a port (ADR-0023)
The Tier gate runs through the `IdentityVerificationProvider` port
(`apps/users/identity/`), exactly mirroring the payments port:

- `ManualProvider` — human review today.
- `FakeProvider` — deterministic, for tests.
- Resolved via `registry.get_provider()`.

`KYCEmailVerifyView` calls it via `_run_identity_check()`. A real vendor or an IPRS
lookup drops in as **another adapter** without touching the view (**P-17**). The
same "the edge is pluggable, the core is not" discipline that governs payment rails
governs identity verification.

---

## Part B — Identity is a ledger too (`apps/verification`)

This is the chapter's central idea, and it is the [Philosophy §3](../product/02-philosophy.md)
"immutable log + disposable projection" pattern applied to *identity*:

> Every KYC journey is a **`VerificationCase`** whose immutable **`CaseEvent`**
> timeline is the source of truth. **`KYCProfile.status` is a projection** of that
> timeline.

The parallel to money is exact and intentional:

| Money (ledger) | Identity (verification) |
|----------------|-------------------------|
| `post_journal()` — the one money door | `verification.service.decide()` — the one decision door |
| `JournalEntry` / `JournalLine` (immutable) | `CaseEvent` (immutable) |
| Transition rules enforced at the door | declared **transition table** enforced at the door |
| `AccountBalance` (derived) | `KYCProfile.status` (derived) |

### `decide()` — the one door for identity state (P-10)
All review decisions — ops console, Django-admin actions/form, automated provider
outcomes — go through `apps.verification.service.decide()`. It enforces the declared
transition table and appends the `CaseEvent`. Nothing mutates case or KYC review
state by editing rows. This is why identity is as trustworthy as money: it has the
same single, disciplined door.

### Evidence is versioned, never overwritten (P-11)
Documents are versioned **`CaseDocument`** rows pinned to their storage objects. A
re-submission *adds a version*; it never overwrites the evidence a prior decision
was made against. So an auditor (or a regulator, Phase 8) can always see *exactly*
the evidence any decision used — the identity analogue of an immutable journal line.

---

## Part C — Staff identity & operator authority (`apps/backoffice`)

### Staff accounts
Operators are `StaffAccount` rows: corporate email + password, admin-provisioned,
`must_change_password` on first login, **no self-serve reset** (a reset path is an
attack surface for the most powerful accounts). They authenticate with a dedicated
staff JWT (`apps/backoffice/auth.py`, `type: "ops"`), wholly separate from customer
SimpleJWT.

### Capabilities (RBAC)
Authority is a **code-defined capability map** (`capabilities.py`) over `ops:*`
Django Groups, enforced server-side via `RequireCapability`. Capabilities are the
[Governance](13-governance-architecture.md) principle applied to staff: a
centralized, code-reviewed authority definition rather than per-view checks.

### Every action is audited (P-14, ADR-0019)
Every `/api/ops/*` action writes an append-only **`AuditEvent`** via
`record_action()`. Operator power over customer money demands a non-repudiable
trail; the audit log is the immutable record that makes operator authority *safe* to
grant. Operators never mutate money or identity directly — money corrections go
through `post_journal()` (a reversing entry), identity decisions through `decide()`
— so even a legitimate operator's actions are expressed in the same immutable,
provable substrate as everything else.

### Separate deployment
The ops console is a separate app and separate deployment, **never co-hosted** with
the customer web app. Physical separation reinforces the identity separation: the
customer surface and the operator surface do not share a process, a session, or a
cookie jar.

---

## The identity model, compressed

- **Two populations, never mixed** — customers (phone+OTP) and staff (email+password),
  separate tokens, separate deployments (**P-12**).
- **Customer verification is tiered and pluggable** — frictionless join, gated
  transact, provider port for the actual check (**P-17**).
- **Identity is a ledger** — immutable `CaseEvent` truth, `decide()` as the one
  door, versioned evidence, projected status (**P-10/P-11**).
- **Operator authority is centralized and audited** — capability map,
  `RequireCapability`, an `AuditEvent` for every action (**P-13/P-14**).

---

*Return to the [Domain index](../README.md#2-domain), or continue to
[Architecture / System Architecture](../architecture/20-system-architecture.md).
For the customer-facing side of onboarding see
[User Journey J1](../product/05-user-journeys.md).*
