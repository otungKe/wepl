# Product / 05 — User Journeys

> The canonical flows, end to end, described at the level of *what happens and why*
> — including where each journey touches the money door, the identity ledger, the
> event bus, and governance. These journeys are the contract product and
> engineering share; a feature that breaks one of them breaks the platform's
> promise.

Each journey names the actors, the trigger, the happy path, the invariants that
must hold, and the notable failure modes (because in a financial product, the
failure path *is* the product — see [Philosophy §7](02-philosophy.md)).

---

## Actors

- **Prospective member** — a person with a phone number, not yet verified.
- **Member** — a verified `users.User` inside one or more communities.
- **Community admin** — a member with elevated role and governance power.
- **Operator** — back-office `StaffAccount`, acting through the ops console.
- **The system** — Celery workers, the outbox relay, the payment rails.

---

## J1 — Onboarding & identity (Tier-0 → Tier-1)

**Trigger:** a person installs the app and enters their phone number.

**Happy path:**
1. Phone number entered → OTP sent (SMS in prod; `000000` accepted in dev/staging
   via `STAGING_OTP_BYPASS`, which production refuses to enable, **P-15**).
2. OTP verified → customer JWT issued (SimpleJWT). The user now exists at **Tier-0**.
3. To unlock money movement, the user submits KYC. This opens a **VerificationCase**
   (`apps/verification`); every step appends an immutable `CaseEvent`.
4. The Tier-0 → Tier-1 gate runs through the `IdentityVerificationProvider` port
   (`ManualProvider` = human review, ADR-0022/0023). The decision is made via
   `verification.service.decide()`; `KYCProfile.status` updates as a *projection*.

**Invariants:** identity truth is the `CaseEvent` timeline (**P-10**); documents
are versioned, never overwritten (**P-11**); the status a member sees is derived,
not authoritative.

**Failure modes:** OTP cache outage → honest `503`, not a silent pass (**P-16**);
KYC rejection → case records the reason, member may re-submit (adding a document
*version*), and the prior evidence remains pinned to the prior decision.

> See [Identity Architecture](../domain/14-identity-architecture.md).

---

## J2 — Create / join a community

**Trigger:** a member creates a new community or accepts an invite.

**Happy path:**
1. Creator sets up the community; becomes its first admin (ownership + lifecycle,
   [ADR-0011](../../adr/0011-community-ownership-and-lifecycle.md)).
2. Others join via invite code or request; membership carries a **member status**
   and a stable **member number**.
3. Roles determine governance power for later privileged actions.

**Invariants:** membership state transitions are explicit and lifecycle-managed;
a community always has a clear owner.

**Failure modes:** join request declined; rejoin after leaving is modelled
explicitly (`rejoined_at`), not faked by re-creating a row.

---

## J3 — Contribute (money in) — *the core money-in journey*

**Trigger:** a member pays into a contribution/welfare/shares fund, or a standing
order fires.

**Happy path:**
1. The member initiates a payment; the app requests a **collection** through the
   `PaymentProvider` port → M-Pesa STK push (Daraja details stay behind the port,
   **P-18**).
2. The member approves on their phone. Safaricom calls back; the callback is
   normalized to a `CallbackEvent` (`apps/mpesa`, `apps/payments`).
3. On success, the service calls **`post_journal()`** with the canonical recipe
   from `posting_map.py` (**P-2**, **P-5**): debit `1000` M-Pesa Float, credit the
   member's sub-ledger liability (and `4000` Fee Revenue for any fee, ADR-0024).
   The posting is **idempotent** on an idempotency key, so a retried callback does
   not double-post.
4. A domain event is `emit()`-ted **in the same transaction** (**P-9**); the
   outbox relay later notifies the member and updates activity/feeds.

**Invariants:** the trial balance stays zero (**P-6**); the member's balance is now
*derived* from the new journal lines (**P-3**); the payment is traceable end-to-end
via its **Financial Transaction** reference (ADR-0025).

**Failure modes:** STK timeout / user cancels → no journal posted, payment marked
failed honestly; callback arrives twice → idempotency key makes the second a no-op;
callback arrives for an unknown payment → suspense handling (`1100`), reconciled by
ops, never silently dropped.

> See [Payments Architecture](../architecture/27-payments-architecture.md) and
> [Financial Architecture](../domain/12-financial-architecture.md).

---

## J4 — Payout (money out) — *governed disbursement*

**Trigger:** a community pays out — a ROSCA cycle disbursement, a welfare claim, a
share redemption.

**Happy path:**
1. The payout is *proposed*. If community rules require it, a **vote** opens;
   authorisation is centralised (**P-13**, ADR-0009) and gated on the configured
   threshold/quorum ([Governance](../domain/13-governance-architecture.md)).
2. Once authorised, the system requests a **payout (B2C)** through the payment port.
3. On rail confirmation, `post_journal()` records it: debit the appropriate
   liability/pool, credit `1000` M-Pesa Float (**P-2/P-5**), idempotently.
4. Event emitted → recipient and community notified.

**Invariants:** a payout that is not authorised by governance *cannot* post; the
disbursement and its authorisation are both in immutable records (ledger + audit /
governance).

**Failure modes:** rail rejects the B2C → no journal, payout marked failed,
retriable; partial/ambiguous rail state → suspense + ops reconciliation, never an
optimistic "paid."

---

## J5 — Emergency advance

**Trigger:** a member requests a short-term advance against the pool.

**Happy path:**
1. Request is evaluated against community rules and controls (limits/velocity,
   [ADR-0007](../../adr/0007-controls-at-posting-chokepoint.md)).
2. If approved (possibly via governance), disbursed via payout, and recorded as a
   **receivable**: debit `1200` Advances Receivable (member sub-ledger under it),
   credit `1000`.
3. Repayment reverses the receivable; interest posts to `4100` Interest Income.

**Invariants:** an advance is always a *receivable on the ledger*, never an
untracked IOU; interest is a canonical posting.

---

## J6 — Member checks "what am I owed / what does the pool hold"

**Trigger:** any member opens a fund.

**Happy path:** the app reads *derived* balances (`AccountBalance` projection) and
the member's **Financial Transactions** (searchable, human-legible). Everything
shown reconciles to journal lines on demand.

**Invariants:** what the member sees is always a projection of the one book of
record — never a separately maintained number that could disagree (**P-1**, **P-3**).

---

## J7 — Operator handles an exception (ops console)

**Trigger:** a reconciliation break, a suspense item, a KYC review, a support
request.

**Happy path:**
1. Operator authenticates with the **staff JWT** (email + password, `type:"ops"`,
   **P-12**), separate from any customer session.
2. Operator acts only within their **capabilities** (`RequireCapability`).
3. Every action writes an **AuditEvent** (**P-14**). Corrections to money go
   through `post_journal()` (a reversing entry), never by editing rows; KYC
   decisions go through `verification.service.decide()`.

**Invariants:** operators never mutate money or identity state directly; every
operator action is non-repudiably logged; ops is a *separate deployment* from the
customer app.

> See [Identity Architecture](../domain/14-identity-architecture.md) (staff) and
> [Security Architecture](../architecture/25-security-architecture.md).

---

## J8 — A domain event fans out (notifications, activity, feeds)

**Trigger:** any business fact worth announcing (J3/J4/J5 all emit one).

**Happy path:** `emit()` writes an `OutboxEvent` in the business transaction;
`process_outbox` delivers it at-least-once by re-firing the `domain_event` signal;
consumers (notifications, activity feed) dedupe on `event_id` and act idempotently.

**Invariants:** a rolled-back business transaction discards its event; a crash never
drops one (**P-9**); a duplicate delivery never double-notifies.

> See [Eventing Architecture](../architecture/26-eventing-architecture.md).

---

## J9 — (Future) A third party builds on Wepl (BaaS)

**Trigger:** an external tenant provisions accounts and moves money via the public
API (roadmap Phase 7).

**Shape:** the tenant is isolated (**P-19**, ADR-0008); they call a public,
versioned API ([API Architecture](../architecture/23-api-architecture.md)); their
money still moves only through `post_journal()` on their tenant's ledger; they
receive webhooks-out driven by the same outbox. **The core is unchanged** — this
journey is the proof that the "operating system" claim is real.

---

## The shape shared by every money journey

Notice the recurring spine across J3–J5: **authorise → move on the rail (via the
port) → record via `post_journal()` idempotently → emit event in the same
transaction → project for reads.** Every money feature Wepl will ever add is a
variation on this spine. When you design a new one, map it onto this shape first;
if it does not fit, either the feature is wrong or you have found a genuine reason
for a new ADR.

---

*Continue to [UX Philosophy & Design System](06-ux-and-design.md).*
