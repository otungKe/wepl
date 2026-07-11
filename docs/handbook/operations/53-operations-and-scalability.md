# Operations / 53 — Operational & Scalability Strategy

> Running Wepl day to day, and growing it without betraying the principles that make
> it trustworthy. Scale is approached the same way as everything else here: **the
> book of record stays one, correct, and consistent; everything around it is made
> horizontally scalable and disposable.**

---

## Part A — Operational strategy

### The operator's job is exception-handling, by design
Wepl is built so the *happy path needs no operator*: money posts itself on confirmed
callbacks, events deliver themselves, projections rebuild themselves. Operators exist
for the **exceptions** — reconciliation breaks, suspense items, KYC reviews, support.
The [ops console](../frontend/40-frontend-architecture.md) is therefore an
exception-handling tool, and every action it offers is capability-gated (**P-13**)
and audited (**P-14**).

### The three recovery playbooks
Operations rests on three clean, distinct recovery classes
([Deployment](51-deployment-strategy.md)):

1. **Roll back code** — a bad release reverts to the previous deploy.
2. **Recover a projection** — a corrupted/lagging `AccountBalance` (or feed, or
   search index) is *rebuilt by replay* from the immutable log. Not a rollback — a
   reconstruction. This is the operational pay-off of the disposable-projection
   design.
3. **Reverse, never rewrite, the ledger** — a money mistake is corrected by a
   *reversing entry* through `post_journal()`, preserving the full history. The
   ledger is never edited.

Knowing which playbook applies to a given incident is the core operational skill,
and the design makes the three genuinely separate rather than tangled.

### Routine operations
- **Reconciliation** — `reconcile_ledger` runs in production (scheduled via Beat)
  and proves the trial balance; suspense is worked down by ops.
- **Standing orders / reminders** — scheduled via Celery Beat.
- **KYC review** — the human `ManualProvider` queue, decided through `decide()`.
- **Onboarding operators** — admin-provisioned `StaffAccount`s,
  `must_change_password`, no self-serve reset.

### Incident response priorities
Match the [alerting order](52-observability.md): financial integrity (trial balance,
suspense) first, honest availability (boot/auth) second, ordinary performance third.
A non-zero trial balance is an all-hands event; a latency spike is not.

### Degradation is operated, not feared
The system degrades honestly under dependency loss (**P-16**): a Redis outage means
lagging delivery and honest `503`s, not corruption. The operational response is to
*restore the dependency and let the outbox drain*, not to scramble to protect the
book of record — which was never at risk (commits #155–#157).

## Part B — Scalability strategy

### The scaling philosophy
**Concentrate correctness; distribute everything else.** There is exactly one thing
that must be strongly consistent — the ledger in Postgres — and it is deliberately
kept small and fast. Everything else (the API tier, workers, delivery, projections,
caches) is designed to scale horizontally and to be rebuildable, so growth is a
matter of adding replicas, not rethinking correctness.

### Scaling the tiers

| Tier | How it scales | Bounded by |
|------|---------------|------------|
| **API (Daphne/ASGI)** | horizontal — stateless behind the load balancer; JWT auth carries no server session (revocation via the registry) | — |
| **Celery workers** | horizontal — add workers; queues (`default, notifications, payments, financial`) isolate concerns so notifications can't starve money work | broker throughput |
| **Beat** | singleton scheduler (by design) | — |
| **Redis** | vertical + a bounded connection pool (commit #155) so an outage can't exhaust connections | memory/throughput |
| **Postgres (Neon)** | read scaling via the derived `AccountBalance` projection (indexed) + read replicas; write path kept lean | single-writer consistency |

### The projection is the read-scaling strategy
Balances are read from the **indexed `AccountBalance` projection**, not computed by
scanning journal lines (**P-3**). This is *why* the ledger-first design does not
sacrifice read performance: writes go to the immutable log; reads hit a fast
projection; the two are reconciled by construction. As read volume grows, the
projection (and other read models — feeds, search) scale out independently of the
write path.

### The queue isolation is the fairness strategy
Routing async work into `default / notifications / payments / financial` queues means
a spike in one concern (a notification storm) cannot delay another (money posting).
Under load, money work has its own lane. This is capacity isolation designed in from
the start, not a fix applied after the first incident.

### Multi-tenancy is the horizontal-scale seam (Phase 6/7)
The tenant boundary (**P-19**, [ADR-0008](../../adr/0008-multi-tenancy.md)) is not
only an isolation control — it is the natural **sharding seam**. As Wepl grows into
BaaS (Phase 7), tenants can be distributed across database shards along a boundary
that already exists in the domain, rather than by a painful late re-partitioning.
The [module boundaries](../architecture/22-module-boundaries.md) also leave the
ledger as a clean service-extraction seam if the monolith is ever outgrown.

### Multi-currency scales the model, not the mechanism
Per-currency balancing ([Financial §10](../domain/12-financial-architecture.md),
Phase 5) means adding a currency is data, not a new subsystem — the ledger balances
within each currency using the same posting mechanism. Scale in *product surface*
(currencies, rails, products) is absorbed by the same core, which is the whole
[Vision](../product/01-vision.md).

### The immediate scaling step
The near-term operational/scaling gap (from the audit) is **separating Celery from
the web dyno** — running worker + beat as independently scaled services so async
bursts never degrade request latency ([Infrastructure §Current vs target](50-infrastructure.md)).
This is the first concrete step on the path this chapter describes.

## What scaling must never compromise

- **Never split the book of record into multiple writable copies for "scale"**
  (**P-1**) — that is drift by another name. Scale reads via projections, not by
  forking truth.
- **Never scale by relaxing an invariant** — the trial balance stays provably zero at
  any scale (**P-6**).
- **Never let a cross-cutting concern (limits, audit) fragment across shards** — it
  stays at the one door (**P-2**) even as the door serves more tenants.
- **Never trade honest degradation for throughput** — a faster lie is still a lie
  (**P-16**).

---

*Return to the [Operations index](../README.md#6-operations), or continue to
[Program / Roadmap & Milestones](../program/60-roadmap-and-milestones.md).*
