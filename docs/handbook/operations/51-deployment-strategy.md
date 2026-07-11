# Operations / 51 — Deployment Strategy

> How change reaches production safely. Deployment is the last mile of the
> [Development Workflow](../engineering/34-development-workflow.md), and in a money
> platform it carries one non-negotiable: **a deploy must never be able to unbalance
> the ledger or leave the schema and the models disagreeing.**

Grounded in `render.yaml` (blueprint) and the CI gates.

---

## The pipeline

```
  merge to default ──► CI gates (already green pre-merge) ──► Render deploy
                                                                │
                          ┌─────────────────────────────────────┘
                          ▼
        start.sh: migrate ──► collectstatic ──► launch Daphne (ASGI)
                          │
                          └── production.py boot guard (P-15) — refuses to
                              start if STAGING_OTP_BYPASS && !DEBUG
```

Deployment is driven by the **Render blueprint** (`render.yaml`), a declarative
description of the services, so the deployed topology is version-controlled and
reproducible rather than click-configured.

## The gates that must be green *before* a deploy exists

By the time code merges, it has already passed the
[merge-blocking CI gates](../engineering/33-testing-strategy.md):

- **Migration-drift check** — the schema matches the models, so the release's
  `migrate` cannot surprise production with an un-generated migration.
- **Trial-balance / reconcile** and the **ledger-core coverage floor** — the money
  core is proven before it ships.
- **Grep-guards** — no legacy ledger or mutable balance cache has crept in.

Deployment does not re-litigate these; it trusts that a merge implies green. The
principle (E-7, **P-22**) is that a red gate never becomes a deploy in the first
place.

## Release-time migrations

`start.sh` runs `migrate` as part of release. This is safe *because* of the
additive-first discipline (**P-7**, E-2):

- **Migrations are additive-first.** A money-touching change dual-writes and verifies
  before dropping anything, so a migration deployed ahead of (or behind) the code by
  a moment does not break the running system. Backfills (member numbers, account
  UIDs, pool control accounts — migrations 0011–0020) ran alongside the old shape.
- **Invariants ship in migrations.** The ledger's balance-checking deferred trigger
  is created by migration — so the schema itself enforces conservation of money from
  the moment it is applied ([Data Architecture](../architecture/24-data-architecture.md)).
- **Migrations are reversible where possible**, keeping every change reversible at
  the VCS and schema level.

## The boot guard is part of the deploy contract

Every production start runs the **`production.py` boot guard**: if
`STAGING_OTP_BYPASS` is set while `DEBUG=False`, the process **refuses to start**
(**P-15**). A misconfigured deploy fails *closed* — it does not come up insecure. The
audit's High-severity finding of `STAGING_OTP_BYPASS=true` in the prod env is exactly
what this guard turns from a silent breach into a loud, refused boot.

## Environments

| Environment | Compute | Database | Auth bypass |
|-------------|---------|----------|-------------|
| **Development / CI** | local / GitHub Actions | local PG / CI PG | `STAGING_OTP_BYPASS` allowed (`000000`) |
| **Staging** | Render | **separate Neon branch/database** | bypass allowed (it's not prod) |
| **Production** | Render | Neon production (direct, `sslmode=require`) | **bypass forbidden — boot guard** |

Staging on a *separate Neon branch* means schema and data experiments are fully
isolated from production ([Infrastructure](50-infrastructure.md)). The environments
share the code and the settings-layer shape (`base` → `development`/`production`) so
that "works in staging" means something.

## Secrets and blueprint safety

- Secrets are env vars on the service, not in the blueprint.
- **A blueprint sync does not delete env vars set directly on a service** — so the
  Neon `DATABASE_URL` and rail keys survive a redeploy. This is a deliberate safety
  property: a routine blueprint change can never accidentally strip production's
  database connection.
- `PYTHON_VERSION` + `.python-version` keep the runtime pinned to CI's version.

## Rollback

- **Code:** every change is reversible at the VCS level (E-2); a bad release is
  rolled back to the previous deploy.
- **Data/projections:** a corrupted *projection* is rebuilt by replay from the
  immutable log (not a rollback — a *recovery*,
  [Data Architecture](../architecture/24-data-architecture.md)); the immutable
  ledger itself is never "rolled back" — a mistake is corrected by a *reversing
  entry* through `post_journal()`, preserving the full history.
- **Database:** Neon's backup/PITR posture covers the one irreplaceable store.

The distinction matters: **you roll back code, you recover projections, and you
reverse — never rewrite — the ledger.** Three failure classes, three defined
answers.

## Zero-downtime posture (target)

- ASGI/Daphne behind Render's rolling deploy.
- Additive migrations so old and new code can briefly coexist during a rollout.
- Async work (Celery) is idempotent and at-least-once, so a worker restart mid-deploy
  loses nothing ([Eventing](../architecture/26-eventing-architecture.md)) — the
  outbox drains after the restart.

## What a deploy must never do

- **Never ship a schema that disagrees with the models** (the drift gate prevents it).
- **Never come up with the OTP bypass active in production** (the boot guard prevents
  it).
- **Never require a destructive migration ahead of a verified additive path** (E-2).
- **Never bypass a red gate to "just deploy the fix"** (E-7) — fix the gate's cause.

---

*Continue to [Observability](52-observability.md).*
