# Operations / 50 — Infrastructure

> Where Wepl runs. The infrastructure is deliberately modest and boring
> (**P-21/E-1**) — a managed compute platform, a managed Postgres, a managed Redis,
> S3-compatible storage — chosen so that the interesting risk lives in the ledger's
> correctness, not in the plumbing.

Grounded in `render.yaml` (the blueprint) and `config/settings/production.py`.

---

## The topology

```
                 Render (compute)                         Neon (Postgres)
  ┌────────────────────────────────────────┐        ┌──────────────────────┐
  │  wepl-api    (web, Python/Daphne ASGI)  │───────►│  production database  │
  │  wepl-web    (Next.js, Node)            │        │  (direct, sslmode=require,│
  │  wepl-redis  (managed Redis)            │        │   CONN_HEALTH_CHECKS)  │
  │  [Celery worker + beat]                 │        │  staging = separate    │
  └────────────────────────────────────────┘        │  Neon branch/database  │
        │                                            └──────────────────────┘
        ▼
  Object storage (S3 / Cloudflare R2)  ── KYC media, profile photos (django-storages/boto3)
  Sentry ── errors & observability
  M-Pesa (Daraja) ── payment rail (STK / B2C / callbacks)
  Africa's Talking (SMS) · Brevo (email) · Firebase (push) ── delivery channels
```

## The components

| Component | Provider | Why |
|-----------|----------|-----|
| **API tier** (`wepl-api`) | Render web service, Python, `bash start.sh` | ASGI via Daphne; serves REST + Channels + the money door |
| **Member web** (`wepl-web`) | Render web service, Node | Next.js member app |
| **Redis** (`wepl-redis`) | Render managed | broker + cache + Channels layer |
| **Celery worker + beat** | Render (target: separate services) | async work, scheduled work |
| **PostgreSQL** | **Neon** (not Render) | the single store of record |
| **Object storage** | S3-compatible (R2/S3) | durable KYC media (never dyno disk) |
| **Errors** | Sentry | observability ([ADR-0020](../../adr/0020-observability-standard.md)) |

## Why Postgres is on Neon, not Render

A deliberate split: **compute on Render, the book of record on Neon.** Neon gives:

- **Branching** — staging is a *separate Neon branch/database*, so staging data and
  schema experiments never touch production. Data-residency (Phase 8) also composes
  with Neon's region model.
- **Autosuspend economics** — cost control for non-prod and low-traffic tiers;
  `production.py` sets `CONN_HEALTH_CHECKS` so an autosuspend wake-up reconnects
  transparently rather than erroring.
- **Direct, non-pooled connection with `sslmode=require`**, carried as `DATABASE_URL`
  set **directly on the service** in the Render dashboard (parsed via
  `dj-database-url`), with discrete `DB_*` vars as a fallback.

The book of record living on a database platform chosen *for the database* — rather
than as a compute-platform add-on — reflects that Postgres is the one component whose
correctness and durability are non-negotiable ([Data Architecture](../architecture/24-data-architecture.md)).

## Nothing authoritative outside Postgres

A recurring infrastructure invariant: **Redis holds nothing whose loss corrupts
truth** — broker messages, cache, ephemeral channel state, all rebuildable/replayable.
**Object storage holds immutable bytes** referenced by Postgres rows. So the failure
domains are clean ([System Architecture §Failure domains](../architecture/20-system-architecture.md)):
a Redis outage degrades honestly; only a Postgres loss is a true data incident, which
is why the backup/PITR posture concentrates there.

## Configuration & secrets

- **Settings layer** by environment: `base.py` → `development.py` / `production.py`.
- **Secrets are environment variables** set on the service (M-Pesa keys, `DATABASE_URL`,
  SMS/email creds, `SECRET_KEY`), never committed.
- **Blueprint-sync safety:** a `render.yaml` blueprint sync does **not** delete env
  vars set directly on a service — a deliberate property so that operationally-set
  secrets (like the Neon `DATABASE_URL`) survive a blueprint redeploy.
- **Version pinning:** `PYTHON_VERSION` + `backend/.python-version` pin Python 3.12
  so Render cannot drift from CI ([Technology Stack](../architecture/21-technology-stack.md)).

## The production boot guard

`production.py` **refuses to boot** if `STAGING_OTP_BYPASS` is set while
`DEBUG=False` (**P-15**). Infrastructure enforces a security invariant at startup:
the system would rather fail to start than start with a total auth bypass
([Security Architecture](../architecture/25-security-architecture.md)). In production,
`SMS_BACKEND=console` routes real OTP codes to the logs where they are operationally
retrievable but not sent over an unconfigured SMS path.

## Current state vs target (an honest gap)

The 2026-06 audit flagged two infrastructure compromises made on the free tier:

1. **Celery folded into the web dyno** (Medium) — on the free plan the worker has at
   times shared the web process. The *target* (and the reason the component table
   lists them separately) is **independently deployed and scaled** worker + beat
   services, so a burst of async work cannot degrade request latency
   ([Scalability](53-operations-and-scalability.md)).
2. **KYC media on ephemeral disk** (High) — **closed**: media now lives in durable
   S3/R2 object storage (`USE_S3`, `django-storages`).

This handbook states the target and names the gap ([Charter](../00-charter.md)); the
worker separation is the tracked next infrastructure step.

## Local and CI parity

- **Local full stack:** `docker-compose up` brings web + Celery worker + beat +
  Postgres + Redis + Daphne — the same shape as production, so local matches prod.
- **CI:** provisions Postgres 16 + Redis 7 as services so the suite runs against real
  dependencies ([Testing Strategy](../engineering/33-testing-strategy.md)) — the
  ledger's invariants cannot be proven against a mocked database.

---

*Continue to [Deployment Strategy](51-deployment-strategy.md).*
