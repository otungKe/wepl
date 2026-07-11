# Product / 04 — Business Model

> How Wepl creates value for communities and captures a fair share of it. This
> chapter is deliberately architecture-aware: the ledger and the port/adapter
> design are what make several of these revenue lines *possible without re-work*,
> which is itself a strategic asset.

---

## Who pays, and for what

Wepl serves **groups**, but value and willingness-to-pay concentrate at three
levels, and the model addresses each.

| Payer | What they're buying | Why they'll pay |
|-------|--------------------|-----------------|
| The community (via its members) | Trustworthy shared money infrastructure | It replaces a fallible treasurer and a fragile spreadsheet; the pool is provably correct. |
| The individual member | Legibility and access to collective products (advances, payouts, welfare) | They can see what they're owed and get money when the group's rules allow. |
| Third parties (future) | The ledger-first core, as BaaS | They avoid building accounting, rails, identity, and governance themselves. |

## Revenue lines

The platform already models fees, excise duty, and withholding as **canonical
ledger postings** ([ADR-0024](../../adr/0024-fee-and-tax-postings.md)), which means
new revenue lines are new posting recipes, not new subsystems. That is the
business-model advantage of the ledger-first design: pricing is expressed in the
book of record, so it is auditable and reconcilable by construction.

### 1. Transaction fees (primary, today)
A fee on money movements — contributions in, payouts out — posted to `4000` Fee
Revenue. Transparent to members (they see the fee as a ledger line), and reconciled
like all other money. The unit economics ride on top of the underlying rail cost
(e.g. M-Pesa tariffs), so the design keeps the rail cost visible and the margin
explicit.

### 2. Financial products (near)
Margin on collective financial products the ledger already supports:
- **Emergency advances** — interest on advances against the pool, posted to `4100`
  Interest Income.
- **Shares / investment pools** — a management take on pooled equity products.
These are high-trust products that *only* work because the ledger can prove the
pool's state; they are unavailable to a spreadsheet-based competitor.

### 3. Subscription / SaaS (near–mid)
A per-community subscription for advanced capability — larger membership, richer
governance, reporting exports, priority support. The ops console, reporting/GL
(Phase 4), and governance are the value here. Subscriptions suit larger, more
formal groups (registered SACCOs, welfare associations) that value features over
per-transaction cost.

### 4. Float / treasury economics (mid)
As balances rest in the platform's settlement position between collection and
payout, there is treasury income to be earned — but only within a compliant
treasury design (Phase 8). This line is **deliberately not** pursued ahead of the
controls that make it safe and lawful; the ledger makes the float position exactly
knowable, which is the precondition for touching it responsibly.

### 5. Banking-as-a-Service (long)
The strategic endgame (roadmap [Phase 7](../../roadmap/PHASE-7-baas.md)): external
fintechs and institutions run their own collective-money products on Wepl's
tenant-isolated ledger, paying per API call / per account / per volume. This is
where "operating system" becomes literal revenue: Wepl is paid to *be the
infrastructure*. Everything in Horizons 1–2 of the [Vision](01-vision.md) is also
the R&D that de-risks this line.

## Why the architecture is the moat

The business defensibility is not the app UI — that is copyable. It is:

1. **A provably correct ledger of collective money.** Trust compounds; a group
   that has years of clean, reconciled history on Wepl cannot cheaply be lured to a
   competitor that starts from zero trust.
2. **One core, many products.** Because rails, currencies, and products plug into
   one posting chokepoint (P-17), Wepl can expand its product surface faster than a
   competitor who bolts each product onto bespoke balance logic.
3. **Compliance-ready by construction.** The identity ledger and audit log mean
   Wepl can enter regulated markets that a ledgerless competitor cannot follow into
   without a rewrite.

## Pricing principles

- **Fees are ledger lines, visible to the member.** We never hide the cost of
  money movement; transparency *is* the trust product (Philosophy §1, §7).
- **The group, not the individual, is the pricing unit** wherever possible — it
  aligns with who we serve.
- **Rail cost stays explicit**, so margin decisions are honest and the platform is
  never quietly underwater on a transaction.
- **No revenue line ships ahead of the controls that make it safe** (see float/
  treasury above). Compliance gates monetisation, not the reverse.

## Market entry

Kenya first, because M-Pesa gives near-universal, low-friction rails and because
collective informal finance (chamas, welfare groups, SACCOs) is deep, mainstream,
and underserved by software. The M-Pesa-specific parts are quarantined behind the
payment port (P-18), so the *market-entry* dependency on one rail does not become
an *architectural* dependency — expansion to another country/rail is an adapter,
not a rebuild.

---

## Open questions (tracked, not decided here)

- Exact fee levels and tiering — a pricing exercise, not an architectural one.
- Whether subscription or transaction fees lead for formal SACCOs.
- Regulatory licensing path for treasury and BaaS lines (Phase 8 scope).

These are business decisions to be made with data; the architecture is built so
that whichever way they resolve, the answer is *configuration and posting recipes*,
not new financial subsystems.

---

*Continue to [User Journeys](05-user-journeys.md). See also
[Vision](01-vision.md) and [Roadmap](../program/60-roadmap-and-milestones.md).*
