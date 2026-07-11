# Architecture / 24 — Data Architecture

> How data is stored, derived, migrated, retained, and isolated. The governing
> idea, repeated from the [Philosophy](../product/02-philosophy.md), is
> **immutable truth + disposable projection**: the data that matters is an
> append-only record, and the data we read fast is a cache we can rebuild.

---

## The stores and what belongs in each

| Store | Holds | Authoritative? |
|-------|-------|----------------|
| **PostgreSQL (Neon)** | Ledger, projections, cases, audit, outbox, all domain models | **Yes — the single store of record** |
| **Redis** | Cache, Celery broker messages, Channels ephemeral state | **No — rebuildable/replayable only** |
| **Object storage (S3/R2)** | KYC documents, media, pinned to versioned records | Yes for the *bytes*; the record that points to them lives in Postgres |

The rule: **anything authoritative lives in Postgres.** Redis holds nothing whose
loss would corrupt truth (which is why a Redis outage degrades but does not corrupt
— [System Architecture §Failure domains](20-system-architecture.md)). Object storage
holds the immutable *bytes* of evidence, referenced by Postgres rows that carry
their identity and version.

## Immutable-log tables vs projection tables

The single most important data-architecture distinction, applied in four places
([Domain Model §Cross-cutting truths](../domain/10-domain-model.md)):

| Immutable log (append-only, never UPDATE/DELETE) | Projection (mutable, rebuildable) |
|--------------------------------------------------|-----------------------------------|
| `JournalEntry` / `JournalLine` | `AccountBalance` |
| `CaseEvent` | `KYCProfile.status` |
| `AuditEvent` | ops read models |
| `OutboxEvent` | delivery state |

- **Immutable-log tables are write-once.** Corrections are *new rows* (a reversing
  journal entry, a new case event), never edits. This is what makes the history
  trustworthy: you cannot rewrite what happened.
- **Projection tables are derived and rebuildable.** `AccountBalance` can be
  reconstructed by replaying journal lines; a corrupted projection is a *replay*,
  not an incident. Projections may carry a "rebuilt-from" watermark so a rebuild is
  a well-defined operation.

When you add a table that holds important truth, classify it into one of these two
kinds *first*. A table that is neither cleanly-immutable nor cleanly-derived is a
future drift bug.

## Keys, identity, and idempotency

- **Money identity is stable and code-independent.** An `Account`'s identity is
  `id`/`account_uid`; its human `code` is display metadata that can be
  restandardised without breaking references ([ADR-0025](../../adr/0025-financial-account-and-pool-identity.md)).
  This decoupling is why the COA codes could be re-standardised (migrations
  0010–0014) without a data crisis.
- **Idempotency keys are unique constraints**, not application checks:
  `JournalEntry.idempotency_key` is `unique`, so the *database* guarantees a replay
  cannot double-post (**P-2/P-6**). Idempotency is enforced by the schema, not by
  hopeful code.
- **Member identity** is the phone number plus a stable **member number** and a
  unified, searchable **transaction reference** (commits #143–#145) — so a human can
  find "their" money without knowing internal IDs.

## Precision and money storage

Money columns are `NUMERIC(20,4)` (`Decimal`), never floating point (**P-4**,
[ADR-0003](../../adr/0003-money-representation.md)). Currency is stored *with* the
amount. The database type is chosen to match the value object exactly, so there is
no lossy boundary between application money and stored money.

## Migrations — a governed, drift-checked process

Migrations are treated as first-class, audited changes to the money substrate:

- **CI fails on model/migration drift** (`makemigrations --check --dry-run`), so the
  schema in the database always matches the models in the code — no silent
  divergence.
- **Migrations carry real invariants.** The ledger's balance-checking **deferred
  constraint trigger** is created *in a migration* — the schema itself, not just the
  app, enforces conservation of money.
- **Data migrations are additive-first** (**P-7**): backfills (e.g. member numbers,
  account UIDs, pool control accounts — migrations 0011–0014, 0018–0020) run
  alongside the old shape before any column is dropped, and are reversible where
  possible.
- **Money-touching migrations are guarded by the green test suite and the
  trial-balance check.** A migration that could unbalance the ledger cannot pass CI.

## Consistency model

- **Strong consistency for truth.** Ledger writes and their balance projection
  commit in one transaction; the DB trigger re-checks the invariant at COMMIT.
  Reads of a balance never see a half-applied entry.
- **Eventual consistency for effects only.** Feeds, notifications, search indexes,
  and external webhooks catch up asynchronously via the outbox — never the book of
  record. Search ([ADR-0017](../../adr/0017-search-architecture.md)) and activity
  feeds ([ADR-0016](../../adr/0016-activity-feed-architecture.md)) are explicitly
  derived, lag-tolerant projections.

## Retention, audit, and the regulator

- **Immutable logs are retained** — the ledger, audit log, and case timeline are the
  records a future auditor or regulator (Phase 8) will demand, so they are not
  pruned; they are the memory of the platform.
- **Media is retained and versioned** — a `CaseDocument` version is never
  overwritten (**P-11**), so the evidence behind any past decision is always
  recoverable.
- **Projections and caches are freely disposable** — pruning or rebuilding them
  carries no historical loss.

## Data residency and isolation (forward-looking)

- **Tenancy is the isolation boundary** (**P-19**, [ADR-0008](../../adr/0008-multi-tenancy.md)):
  data is scoped so a tenant can only ever reach its own rows. This is threaded
  through new models from the start, not retrofitted.
- **Data residency** (Phase 8) — the ability to pin a tenant's data to a
  jurisdiction — is a natural extension of the tenant boundary plus Neon's
  branching/region capabilities. It is designed-for (the boundary exists) but not
  yet built.

## Backups and recovery

Postgres (Neon) is the one store whose loss is unrecoverable, so it carries the
platform's backup and PITR posture; staging runs on a separate Neon branch. Redis
and object storage are recoverable-or-rebuildable by design. Recovery of a
*projection* is a replay from the immutable log; recovery of the *database* is a
restore — the two failure classes have two different, well-defined answers. See
[Infrastructure](../operations/50-infrastructure.md).

---

*Continue to [Security Architecture](25-security-architecture.md).*
