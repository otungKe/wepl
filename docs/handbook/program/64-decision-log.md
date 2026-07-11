# Program / 64 — Decision Log

> The annotated index of Architecture Decision Records — the platform's **case law**.
> Each ADR is one immutable decision; this log says, in a line, what it decided, which
> [principle](../product/03-principles.md) it grounds, and which handbook chapter
> elaborates it. The authoritative ADR index and template live in
> [`docs/adr/`](../../adr/README.md).

---

## How to use this log

- **The handbook says the enduring shape; the ADR says why we chose it.** When a
  chapter makes a claim, this log points you to the decision behind it.
- **ADRs are immutable.** To change a decision, a new ADR supersedes the old one
  (noted in both); the affected handbook chapter is then revised in place
  ([Documentation Standards](../engineering/35-documentation-standards.md)).
- **Structural changes require an ADR before they're built** (**P-20**, E-9).

---

## The ledger core (the foundation)

| ADR | Decides | Principle | Chapter |
|-----|---------|-----------|---------|
| [0001](../../adr/0001-ledger-first-double-entry.md) | Double-entry ledger is the single book of record | **P-1** | [Financial](../domain/12-financial-architecture.md) |
| [0002](../../adr/0002-remove-legacy-ledger-and-mutable-balances.md) | Delete the legacy single-entry ledger and mutable balance fields | **P-3** | [Financial](../domain/12-financial-architecture.md), [Coding Standards](../engineering/31-coding-standards.md) |
| [0003](../../adr/0003-money-representation.md) | Money = `Decimal(20,4)` + `Money` value object + currency | **P-4** | [Financial §7](../domain/12-financial-architecture.md), [Stack](../architecture/21-technology-stack.md) |
| [0004](../../adr/0004-post-journal-single-entrypoint.md) | `post_journal()` is the single money-mutation entrypoint | **P-2** | [Financial §2–3](../domain/12-financial-architecture.md) |
| [0025](../../adr/0025-financial-account-and-pool-identity.md) | Financial-account identity (`account_uid`) + pools as first-class accounts | **P-3** | [Financial §4–5](../domain/12-financial-architecture.md), [Data](../architecture/24-data-architecture.md) |
| [0024](../../adr/0024-fee-and-tax-postings.md) | Canonical fee, excise-duty, withholding postings | **P-5** | [Financial §6](../domain/12-financial-architecture.md), [Business Model](../product/04-business-model.md) |

## Rails, eventing, controls, reporting (the platform layer)

| ADR | Decides | Principle | Chapter |
|-----|---------|-----------|---------|
| [0005](../../adr/0005-payment-provider-abstraction.md) | `PaymentProvider` port/adapter abstraction | **P-17/P-18** | [Payments](../architecture/27-payments-architecture.md) |
| [0006](../../adr/0006-transactional-outbox.md) | Transactional outbox for durable domain events | **P-9** | [Eventing](../architecture/26-eventing-architecture.md) |
| [0007](../../adr/0007-controls-at-posting-chokepoint.md) | Limits & risk controls at the posting chokepoint | **P-2** | [Financial §8](../domain/12-financial-architecture.md) |
| [0014](../../adr/0014-payment-aggregate-and-reconciliation.md) | Payment aggregate + rail reconciliation | — | [Payments §Idempotency](../architecture/27-payments-architecture.md) |

## Identity, access, audit (the trust layer)

| ADR | Decides | Principle | Chapter |
|-----|---------|-----------|---------|
| [0009](../../adr/0009-centralized-authorization-policy.md) | Centralized authorization policy | **P-13** | [Governance](../domain/13-governance-architecture.md), [Security](../architecture/25-security-architecture.md) |
| [0010](../../adr/0010-session-registry-and-token-revocation.md) | Session registry + token revocation | — | [Identity §A](../domain/14-identity-architecture.md), [Security](../architecture/25-security-architecture.md) |
| [0011](../../adr/0011-community-ownership-and-lifecycle.md) | Community ownership & lifecycle | — | [Governance](../domain/13-governance-architecture.md) |
| [0019](../../adr/0019-append-only-audit-log.md) | Append-only operator audit log | **P-14** | [Identity §C](../domain/14-identity-architecture.md), [Security](../architecture/25-security-architecture.md) |
| [0022](../../adr/0022-two-tier-access-model.md) | Two-tier (Tier-0 → Tier-1) access model | **P-12** | [Identity](../domain/14-identity-architecture.md) |
| [0023](../../adr/0023-identity-verification-provider.md) | Identity-verification provider port/adapter | **P-10/P-17** | [Identity §A–B](../domain/14-identity-architecture.md) |

## Product & supporting contexts

| ADR | Decides | Principle | Chapter |
|-----|---------|-----------|---------|
| [0013](../../adr/0013-contributions-module-split.md) | Split the contributions god-module along sub-domain seams | — | [Module Boundaries](../architecture/22-module-boundaries.md) |
| [0012](../../adr/0012-chat-scaling.md) | Chat scaling (Channels) | — | [System](../architecture/20-system-architecture.md), [Frontend](../frontend/40-frontend-architecture.md) |
| [0015](../../adr/0015-multi-channel-notification-delivery.md) | Multi-channel notification delivery | **P-9** | [Eventing](../architecture/26-eventing-architecture.md), [Stack](../architecture/21-technology-stack.md) |
| [0016](../../adr/0016-activity-feed-architecture.md) | Activity feed architecture | **P-8** | [Data](../architecture/24-data-architecture.md) |
| [0017](../../adr/0017-search-architecture.md) | Search architecture | **P-8** | [Data](../architecture/24-data-architecture.md) |
| [0018](../../adr/0018-file-storage-and-media-pipeline.md) | File storage & media pipeline | **P-11** | [Data](../architecture/24-data-architecture.md), [Security](../architecture/25-security-architecture.md) |

## Cross-cutting (scale, boundaries, conventions, observability)

| ADR | Decides | Principle | Chapter |
|-----|---------|-----------|---------|
| [0008](../../adr/0008-multi-tenancy.md) | Multi-tenancy boundary + isolation | **P-19** | [Data](../architecture/24-data-architecture.md), [Scalability](../operations/53-operations-and-scalability.md) |
| [0020](../../adr/0020-observability-standard.md) | Observability standard | — | [Observability](../operations/52-observability.md) |
| [0021](../../adr/0021-api-conventions.md) | API conventions | — | [API](../architecture/23-api-architecture.md) |

---

## Reading the log as a story

The ADRs, read in dependency order, tell the platform's story:

1. **Decide the foundation** (0001–0004, 0024–0025): the ledger is the one book of
   record, money is `Decimal`, `post_journal()` is the one door, accounts have stable
   identity.
2. **Make the edges pluggable** (0005, 0023): payments and identity verification
   become ports, so rails and vendors are adapters.
3. **Make effects durable** (0006, 0014–0018): the outbox never loses an event, and
   notifications/feeds/search/media are lag-tolerant projections off it.
4. **Make authority safe** (0009–0011, 0019, 0022): centralized authz, revocable
   sessions, community lifecycle, an immutable audit log, and the two-population
   split.
5. **Make it scale and stay clean** (0007, 0008, 0012, 0013, 0020, 0021): controls at
   the chokepoint, the tenant boundary, chat scaling, the god-module split,
   observability, and API conventions.

Each decision assumes the ones before it. That ordering is not accidental — it is the
[roadmap's sequencing thesis](60-roadmap-and-milestones.md) expressed as decisions:
the foundation first, because everything else is cheap on top of it and impossible
without it.

## Gaps in the record (honest notes)

- **(Reconciled 2026-07-11.)** The ADR index README was stale — it listed only 10 of
  25 ADRs and marked several shipped decisions (0005/0006/0007/0025) as *Proposed*.
  The index has been rebuilt: **every ADR is now Accepted except 0024**, whose fee
  postings are built but whose excise-duty/withholding legs await business/compliance
  inputs. This was the first act of Workstream A in the
  [Convergence Plan](61-convergence-plan.md) (CV-01) — a live example of the
  [Charter](../00-charter.md)'s rule that code and record must not silently diverge.
- **The Phase 7 (BaaS) decisions are now drafted** as **ADRs 0026–0029** (Proposed):
  public API surface & versioning (0026), per-tenant API-key auth (0027), outbound
  webhooks on the outbox (0028), and the sandbox (0029). Per P-20 they precede the
  implementation ([Convergence Plan](61-convergence-plan.md) Workstream D).
- Remaining future decisions (AML monitoring design, service-extraction triggers, the
  import-contract tool, the ledger↔M-Pesa de-coupling of CV-23) will each earn an ADR
  when they harden from [direction](63-future-evolution.md) into plan.

---

*Return to the [handbook index](../README.md), or to the
[Roadmap](60-roadmap-and-milestones.md).*
