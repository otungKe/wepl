# Architecture / 27 — Payments Architecture

> How money crosses the boundary between Wepl's ledger and the real world's payment
> rails — and how that boundary is drawn so that adding a new rail never touches a
> line of financial logic. This is the port/adapter pattern at its most load-bearing.

Grounded in [ADR-0005](../../adr/0005-payment-provider-abstraction.md) and
[ADR-0014](../../adr/0014-payment-aggregate-and-reconciliation.md); realised in
`apps/payments/` (the port) and `apps/mpesa/` (the M-Pesa adapter).

---

## The one idea

> **The ledger knows nothing about M-Pesa, and M-Pesa knows nothing about the
> ledger.** Between them sits the `PaymentProvider` port, speaking a rail-agnostic
> vocabulary.

Everything in this chapter follows from that separation. It is what lets the
[Vision](../product/01-vision.md) promise "a new rail ships without touching
financial logic" (**P-17**) — and it is what keeps the Kenyan *market-entry*
dependency on M-Pesa from becoming an *architectural* dependency.

## The port

`PaymentProvider` (`apps/payments/providers/`) is the interface every rail
implements. Above it, the entire platform speaks only **normalized results**:

| Normalized type | Meaning |
|-----------------|---------|
| `CollectionResult` | outcome of a money-in request (STK push) |
| `PayoutResult` | outcome of a money-out request (B2C) |
| `CallbackEvent` | a normalized asynchronous rail callback |
| `StatusResult` | a normalized status query |

Providers are resolved via `registry.get_provider()`, so the rest of the code asks
for "the provider" and gets whichever adapter is configured. Code above the port
**must not** import Daraja field names (**P-18**); it deals only in these four
types. This is the rule that keeps the coupling from leaking.

## The adapters

| Adapter | Role |
|---------|------|
| `MpesaProvider` (`apps/payments/providers/mpesa.py` + `apps/mpesa/`) | Adapter #1: all Daraja wire details — STK push, B2C, callback field names, auth, shortcodes | 
| `FakeProvider` | Deterministic adapter for tests and the future BaaS sandbox |

**All Daraja specifics are quarantined** inside the M-Pesa adapter. STK push
mechanics, B2C result/timeout URLs, the exact callback JSON shape, the counterparty
name masking (full for ops, masked for members — commit #154) — these live *only*
there. The `FakeProvider` is not an afterthought; it is what makes money paths
testable without a live rail and what will back the Phase 7 sandbox so integrators
build against realistic behaviour without touching real money.

## The money-in flow (collection)

Tracing [User Journey J3](../product/05-user-journeys.md) precisely:

1. **Request** — a service asks the port for a **collection**; the M-Pesa adapter
   issues an STK push. The member approves on their phone. *No journal yet* — money
   has not moved as far as Wepl can prove.
2. **Callback** — Safaricom calls back asynchronously. The adapter validates
   authenticity and **normalizes** the payload into a `CallbackEvent`. Above this
   point, no Daraja vocabulary exists.
3. **Post** — on a *confirmed success*, the service calls **`post_journal()`** with
   the canonical `posting_map` recipe (Dr `1000` M-Pesa Float · Cr member sub-ledger
   · Cr `4000` Fee Revenue for any fee), inside a transaction, **idempotently** on a
   key derived from the rail reference.
4. **Emit** — a domain event is `emit()`-ted in the same transaction; the outbox
   fans out the member notification and feed update.

The load-bearing rule: **Wepl posts to its ledger only on a confirmed rail
callback, never on the optimistic hope of an STK push.** This is
[UX-3/P-16](../product/06-ux-and-design.md) at the payments layer — we do not
pretend money moved until the rail says it did.

## The money-out flow (payout / B2C)

1. **Authorize** — the payout passes [governance](../domain/13-governance-architecture.md)
   and [controls](../domain/12-financial-architecture.md); an unauthorized payout
   never reaches the port.
2. **Request** — the service asks the port for a **payout**; the adapter issues a
   B2C.
3. **Confirm & post** — on a confirmed B2C result, `post_journal()` records it (Dr
   liability/pool · Cr `1000`), idempotently. A failed B2C posts nothing and is
   retriable.

## Idempotency & reconciliation (ADR-0014)

Rails are an at-least-once, sometimes-ambiguous world: callbacks arrive twice,
arrive late, or arrive for a payment Wepl doesn't recognise. The payment aggregate
and reconciliation design handles all three:

- **Duplicate callback** → the ledger's unique `idempotency_key` makes the second
  post a no-op. Money cannot be double-credited (also a
  [security control](25-security-architecture.md), Defence 4).
- **Unknown/ambiguous inbound money** → lands in **`1100` Suspense**, surfaced to
  ops for reconciliation. Never silently dropped, never optimistically credited.
- **Payment state is reconciled against rail state** (ADR-0014), so Wepl's view of a
  payment and the rail's view converge, with breaks visible to operators rather than
  hidden.

The invariant across all of this: **an ambiguous rail state can delay or suspend
money, but it can never unbalance the ledger.** Suspense is a real account; a
break is a visible, reconcilable item, not a lost shilling.

## Why the port pays off — three times over

The same port abstraction serves three goals with one design:

1. **New rails are adapters, not rewrites** (**P-17**). A bank rail, a card rail, a
   second mobile-money provider — each is a new `PaymentProvider` implementation
   behind the same normalized vocabulary. Nothing in `contributions`, `ledger`, or
   governance changes.
2. **Money paths are testable** without a live rail, via `FakeProvider` — which is
   why the money-core can hold a ≥90% coverage floor (**P-22**).
3. **The BaaS sandbox** (Phase 7) is `FakeProvider` behind a tenant, giving
   integrators realistic behaviour with no real money.

One abstraction, chosen early, unlocks rail expansion, testability, and the
sandbox. That is the return on drawing the boundary correctly.

## What the payments layer must never do

- **Never leak Daraja vocabulary above the port** (**P-18**).
- **Never post to the ledger on an unconfirmed rail action** (optimistic success is
  a lie — **P-16**).
- **Never move money except through `post_journal()`** (**P-2**) — the payments
  layer *requests* rail movement and *records* confirmed movement; it does not
  invent a second money path.
- **Never silently absorb ambiguous money** — that is what suspense and
  reconciliation exist for.

## The rail roadmap

- **Today:** M-Pesa (Kenya), the deep market-entry rail.
- **Next:** additional rails as adapters as Wepl expands — bank rails, card rails,
  other mobile-money networks — each proving the port by *not* touching financial
  logic.
- **Multi-currency** ([Financial Architecture §10](../domain/12-financial-architecture.md),
  Phase 5) composes with multi-rail: a rail settles in a currency, and the ledger
  balances per currency.

---

*Return to the [Architecture index](../README.md#3-architecture), or continue to
[Engineering / Engineering Principles](../engineering/30-engineering-principles.md).*
