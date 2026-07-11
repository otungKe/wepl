# Architecture / 25 — Security Architecture

> The threat model and the defences. In a platform that holds other people's
> money, security is not a feature layer bolted on top — it is a property of the
> same decisions that make the ledger trustworthy. Many of Wepl's security controls
> are the *same* controls that make its money provable; this chapter names them as
> security.

---

## What we are protecting, and from whom

**Assets:** members' money (and the ability to move it), members' identity
documents (KYC), and the integrity of the book of record.

**Adversaries, roughly in order of concern:**
1. An attacker who steals a **customer** session and tries to move that member's
   money.
2. An attacker who tries to **escalate** from a customer identity to operator power.
3. A malicious or compromised **operator** abusing legitimate access.
4. An attacker replaying or forging **payment callbacks** to mint money.
5. An attacker exploiting a **dependency outage** to bypass a control.
6. Bulk **data exfiltration** of KYC media or the ledger.

The defences below map to these.

## Defence 1 — Two populations, structurally separated (P-12)

Customer identities (`users.User`, phone+OTP, SimpleJWT) and operator identities
(`StaffAccount`, email+password, `type:"ops"` JWT) are **separate credentials,
separate tokens, separate deployments** ([Identity Architecture](../domain/14-identity-architecture.md)).
This directly defeats adversary #2: there is no code path that turns a customer
token into an operator token, because the token *kinds* are distinct and the ops
console is a different deployment. The most powerful accounts (operators) have **no
self-serve reset** and are admin-provisioned — removing the classic account-recovery
attack surface on the accounts that matter most.

## Defence 2 — The single money door as a security control (P-2)

Because all money moves through `post_journal()`, there is exactly **one** place to
enforce authorization, limits, and (later) AML on money movement. An attacker who
finds a new endpoint still cannot move money by a novel path, because there is no
novel path — the door is singular and guarded, and CI forbids creating a second
one. Security benefits enormously from the same narrowness the ledger needs for
correctness.

## Defence 3 — Centralized authorization (P-13)

Money authority runs through `FinancialPermissions`; operator authority through the
capability map + `RequireCapability` ([ADR-0009](../../adr/0009-centralized-authorization-policy.md)).
Scattered authorization is authorization that will eventually be *missing* somewhere
— and a missing money check is a breach. One policy layer means one place to review
and one place that cannot be forgotten. This is defence #1 and #3's backbone.

## Defence 4 — Idempotent, callback-driven money (defeats #4)

Money is posted only on **confirmed** rail callbacks, and posting is **idempotent**
on a unique key ([Payments](27-payments-architecture.md)). A replayed or duplicated
M-Pesa callback is a no-op — it cannot mint a second credit. Ambiguous or unknown
inbound money lands in **suspense** (`1100`) for operator reconciliation, never
optimistically credited. Callback authenticity is validated at the M-Pesa adapter
boundary before any normalization. The result: forging or replaying callbacks
cannot create money on the ledger.

## Defence 5 — Honest degradation, never fail-silent (P-16, defeats #5)

A security control that *fails open silently* under load is worse than no control,
because it hides its own absence. Wepl's degradation behaviour is a *decision*, not
an accident (commits #155–#157):

- OTP verification under a cache outage returns an honest **`503`**, not a silent
  pass.
- Throttles **fail open** on a cache outage — a deliberate availability choice — but
  do so *visibly and boundedly* (the Redis cache pool is bounded so an outage
  cannot exhaust connections).
- PIN lockout **fails open** by an explicit, documented choice rather than locking
  out every user on a Redis blip.

Each of these is a *named, reviewed* trade-off between availability and strictness,
recorded so an auditor can see the reasoning — not a surprise discovered during an
incident.

## Defence 6 — The production OTP-bypass guard (P-15)

`STAGING_OTP_BYPASS` accepts a fixed `000000` OTP for frictionless dev/staging. In
production it is a **total auth bypass**, so `production.py` raises
`ImproperlyConfigured` at boot if it is set while `DEBUG=False`. This guard is
**sacred and never weakened**. It converts a catastrophic misconfiguration into a
refused boot — the system would rather not start than start insecure. (The 2026-06
audit flagged `STAGING_OTP_BYPASS=true` in the prod env as High severity precisely
because this guard is the last thing standing between that mistake and a breach.)

## Defence 7 — Everything an operator does is audited (P-14, addresses #3)

A malicious operator cannot be *prevented* by authentication alone — they have
legitimate credentials. The defence is **non-repudiable accountability**: every
`/api/ops/*` action writes an append-only `AuditEvent` via `record_action()`
([ADR-0019](../../adr/0019-append-only-audit-log.md)), and operators never mutate
money or identity directly — corrections go through `post_journal()` (a reversing
entry) and `decide()`. So an operator's every action is expressed in the same
immutable, reviewable substrate as everything else. You cannot make a change that
leaves no trace.

## Defence 8 — KYC media isolation (addresses #6)

KYC documents live in **durable object storage** (S3/R2), never on the ephemeral
dyno disk (a closed High-severity audit finding), pinned to versioned records
(**P-11**). Access is authorized and audited; media is not served from a public,
guessable path. Versioning means evidence cannot be silently swapped.

## Defence 9 — Transport, tokens, and secrets

- **TLS everywhere**; JWTs are bearer tokens over TLS, with a **session registry**
  enabling **revocation** ([ADR-0010](../../adr/0010-session-registry-and-token-revocation.md))
  so a compromised token can be killed, not merely waited out.
- **Secrets** (M-Pesa keys, DB URL, SMS/email creds) are environment variables set
  on the service, never committed; a blueprint sync does not delete env vars set
  directly on the service (a deliberate operational safety property).
- **CORS** is restricted to known origins; the ops console's separate origin is part
  of the plane separation.

## Defence 10 — Tenant isolation (forward-looking, P-19)

As the platform opens up (BaaS, Phase 7), the **tenant boundary** ([ADR-0008](../../adr/0008-multi-tenancy.md))
is the isolation control that ensures one tenant can never read or move another's
money. This is why tenancy is threaded through from the start rather than retrofitted
— cross-tenant leakage is the defining security risk of a BaaS platform, and the
boundary must predate the exposure.

## The security posture, summarized

Wepl's security is **structural, not additive**: the single money door, centralized
authorization, immutable audit, idempotent callbacks, honest degradation, and the
two-population split are the *same* decisions that make the ledger provable. A
security review of Wepl is, to a large degree, a review of whether these structural
properties still hold — which is why the CI gates that protect them (**P-22**) are
themselves security controls.

## Ongoing security practice

- A **`/security-review`** pass on changes that touch auth, money, or KYC.
- The CI grep-guards and coverage floors are treated as security gates, not just
  quality gates.
- New endpoints are reviewed against the plane separation (**P-12**), the money door
  (**P-2**), and the tenant boundary (**P-19**) as a checklist.
- Compliance-grade monitoring (AML, anomaly detection) is a Phase 8 addition that
  hangs off the one money door — the chokepoint that makes such monitoring
  *possible in one place*.

---

*Continue to [Eventing Architecture](26-eventing-architecture.md) and
[Payments Architecture](27-payments-architecture.md).*
