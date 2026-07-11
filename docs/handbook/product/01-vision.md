# Product / 01 — Vision

> Where Wepl is going, and what winning looks like. This chapter is the fixed star
> the rest of the handbook navigates by. If a decision elsewhere does not serve
> this vision, that decision is wrong.

---

## The one-line vision

**Wepl is the financial operating system for money that people manage together.**

Not a bank. Not a wallet. An *operating system*: a trustworthy, ledger-first core
on which any collective-money product — a savings group, a rotating fund, a welfare
pool, an SACCO, a chama, and eventually third-party fintechs — can run without
re-inventing the accounting, the payments, the identity, or the governance.

## The problem, precisely

Across much of the world — and acutely in Kenya, where Wepl begins — enormous
amounts of money are managed **collectively and informally**: chamas, welfare
groups, investment clubs, table-banking circles, ROSCAs. This is not a fringe
activity; it is how a large share of people save, insure themselves, and access
credit. Yet the tools are a treasurer's notebook, a WhatsApp group, a shared
M-Pesa number, and trust that frays under scale.

The failures are predictable and painful:

- **No source of truth.** Balances live in someone's head or spreadsheet. When
  memory and money disagree, the group fractures.
- **No legibility.** Members cannot see, on demand, what they are owed, what the
  pool holds, or where a payment went.
- **No accountability.** The treasurer *is* the system. Fraud, error, and
  disappearance are one person away.
- **No continuity.** When the organiser leaves, the knowledge — and often the
  money — leaves too.

These are not social problems. They are the symptoms of **missing financial
infrastructure.** Wepl exists to supply it.

## What Wepl is

A platform where a group can:

1. **Pool money** with rules everyone can see (contributions, ROSCAs, welfare,
   shares, advances).
2. **Move money** on real rails (M-Pesa today; bank and card rails later) without
   a shared password or a trusted middleman holding the float.
3. **Prove the money** at any instant — every shilling traceable to an immutable,
   double-entry ledger that *cannot* silently disagree with itself.
4. **Decide together** through governance that the software enforces, not merely
   records (votes, quorums, thresholds gating privileged actions).
5. **Trust the system rather than a person** — because the treasurer's authority
   is decomposed into auditable, permissioned operations, not a single point of
   failure.

## What Wepl is *not*

- **Not a neobank chasing individual current accounts.** The individual wallet is
  a means; the *collective* is the unit we serve. Everything about the product
  bends toward groups.
- **Not a ledgerless "fintech UI over a spreadsheet."** The ledger is not an
  implementation detail we could swap for balance columns under deadline. It is
  the product's central claim to trust. See
  [Financial Architecture](../domain/12-financial-architecture.md).
- **Not a closed app.** The long arc is a *platform*: the same core that runs
  Wepl's own products is exposed, tenant-isolated and API-first, so others can
  build on it (BaaS, roadmap Phase 7).

## The arc — three horizons

The [roadmap](../roadmap/README.md) is the detailed plan; here is the shape.

### Horizon 1 — Trustworthy community finance (now)
A polished, correct app for chamas and welfare groups in Kenya. The ledger is the
book of record; M-Pesa is the rail; governance is real. **This is won when a group
that used a notebook would never go back**, because the app is more trustworthy
than any person could be. *(Roadmap Phases 0–4: ledger cutover, rails, eventing,
controls, reporting — done.)*

### Horizon 2 — A financial OS, multi-everything (next)
The core becomes genuinely product-, rail-, and currency-agnostic, and
tenant-isolated. Adding a new money product, a new payment rail, or a new currency
touches *no* financial logic — only configuration and an adapter. **This is won
when Wepl can stand up a second, structurally different money product in days, not
a quarter.** *(Phases 5–6: multi-currency, multi-tenancy — done; Phase 7: BaaS.)*

### Horizon 3 — Regulated financial infrastructure (later)
Wepl operates as compliant financial infrastructure — AML/monitoring, treasury,
data residency, enterprise controls — that other institutions and fintechs run on.
**This is won when a regulated entity is comfortable putting its members' money on
Wepl's ledger.** *(Phase 8: enterprise & compliance.)*

## What winning looks like — the definition of done for the vision

Borrowing the roadmap's own bar, Wepl has realised this vision when:

- The double-entry ledger is the **only** source of monetary truth.
- `post_journal()` is the **sole** money-mutation path and every cross-cutting
  concern (limits, risk, AML, audit, currency, settlement) hangs off it.
- A **global trial balance is provably zero** — in CI and in production
  reconciliation — continuously.
- A **new rail or currency ships without touching financial logic.**
- **Financial statements are generated directly from the general ledger**, not
  reconstructed from application state.

And, at the product level, when **a community's members trust the app more than
they trusted their treasurer** — because trust has moved from a person to a system
that is transparent, provable, and governed.

## The values encoded in the vision

- **Trust is the product.** Everything else is a feature. See
  [Philosophy](02-philosophy.md).
- **The collective is the customer.** Individuals are served *through* their
  groups.
- **Infrastructure over interface.** A beautiful UI on an untrustworthy core is a
  liability; a trustworthy core is the durable asset. We invest accordingly.
- **Open the core, eventually.** The platform's endgame is to be built upon.

---

*Continue to [Philosophy](02-philosophy.md). See also
[Business Model](04-business-model.md) and the
[Roadmap](../program/60-roadmap-and-milestones.md).*
