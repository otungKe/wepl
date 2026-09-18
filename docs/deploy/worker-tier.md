# The async tier: worker + beat as their own services

**Issue:** [#161](https://github.com/otungKe/wepl/issues/161) · residual P0-01 debt ·
closes the "current vs target" row in
[Production_Operations_Roadmap.md](../Production_Operations_Roadmap.md).

## What changed

`backend/start.sh` used to launch the Celery worker and beat in the background of
the web container and then exec Daphne. Three processes, one dyno:

- A notification fan-out or the hourly payment reconciliation competed with HTTP
  requests for the same CPU, so an async burst raised request latency.
- Every web deploy or restart killed in-flight tasks.
- The queue isolation in `CELERY_TASK_ROUTES` (`default`, `notifications`,
  `payments`, `financial`) bought nothing, because one process served all four and
  could not be scaled apart from the API.

There is now one entrypoint per tier:

| Script | Runs | Service |
|---|---|---|
| `backend/start.sh` | migrations, idempotent provisioning, then Daphne | `wepl-api` (web) |
| `backend/start-worker.sh` | `celery worker -Q default,notifications,payments,financial` | `wepl-worker` (worker) |
| `backend/start-beat.sh` | `celery beat` with the database scheduler | `wepl-beat` (worker) |
| `backend/wait-for-migrations.sh` | shared helper the two async scripts call | — |

No correctness risk either way: monetary truth is committed to Postgres by
`post_journal()` before Celery is involved. This is a resilience and scaling
change.

### Who owns migrations

The **web service only**. Three services racing `manage.py migrate` on one
database contend on the same locks, so the async scripts never migrate. They call
`wait-for-migrations.sh`, which polls `migrate --check` (non-zero while
migrations are unapplied *or* the database is unreachable — both are reasons to
keep waiting) for up to `MIGRATION_WAIT_SECONDS`, default 300. After that it
starts anyway and logs a warning rather than exiting, because a long wait is more
often a slow deploy than a broken one.

### Beat runs exactly once

`wepl-beat` is pinned to `numInstances: 1`. A second scheduler re-fires every
entry in `CELERY_BEAT_SCHEDULE`, and `execute_due_standing_orders` firing twice is
a duplicate money movement attempt, not just duplicate work. Duplicating the
*worker* tier is safe and is how it scales.

### The fallback switch

`RUN_EMBEDDED_CELERY=true` on the web service restores the old single-host layout
(worker + beat inside the web process). It exists for a host with no worker tier
and for an emergency rollback, and it defaults to **off**. `render.yaml` declares
it `"false"` explicitly rather than omitting it, so a blueprint re-sync actively
clears a leftover `true` set on the service by hand — the same trick already used
for `STAGING_OTP_BYPASS`.

**Never leave it on while `wepl-beat` is deployed.** That is two schedulers.

## Configuration

| Variable | Default | Where |
|---|---|---|
| `CELERY_QUEUES` | `default,notifications,payments,financial` | worker service; set it to shard queues across services |
| `CELERY_CONCURRENCY` | `2` | worker service |
| `MIGRATION_WAIT_SECONDS` | `300` | worker + beat services |
| `RUN_EMBEDDED_CELERY` | `false` | web service; the rollback switch |

Every credential on `wepl-worker` / `wepl-beat` is copied from the API service
with `fromService` / `envVarKey` rather than re-declared, so each secret is still
entered exactly once in the dashboard and the tiers cannot drift apart.

`SECRET_KEY` in particular **must** be the web service's, not a fresh
`generateValue`: signed download URLs (`apps/files/signing.py`) and the
`FIELD_ENCRYPTION_KEYS` fallback derive from it, so a different key on the worker
silently breaks anything the other tier signed or encrypted. A test asserts this.

## What Harry has to do in the Render dashboard

Nothing in this pull request touches a running service. A blueprint change takes
effect only when the blueprint is synced.

**Render has no free instance type for `type: worker`** — the free plan covers web
services. `wepl-worker` and `wepl-beat` are therefore the first paid services in
the blueprint, at roughly $7/month each (4 services if staging is split too). That
cost is the whole reason this was deferred; it is the decision to make before
syncing.

### 1. Staging first

1. Render dashboard → the `wepl` blueprint → **Sync**. It creates
   `wepl-worker-staging` and `wepl-beat-staging` and sets
   `RUN_EMBEDDED_CELERY=false` on `wepl-api-staging`.
2. Set two secrets **on `wepl-worker-staging`** (they are used by the B2C payout
   call in `apps/ledger/tasks.py`, which now runs on this tier, and they are not
   declared on the API service to be copied from):
   - `MPESA_B2C_INITIATOR_NAME`
   - `MPESA_B2C_SECURITY_CREDENTIAL`
   Set the same two on `wepl-beat-staging` if a sync asks for them.
3. Watch the worker's log for `[wait-for-migrations] schema up to date`, then
   `celery@… ready`, and beat's `Scheduler: Sending due task process-outbox`.
4. Confirm the async tier is actually consuming, from the ops console
   `GET /api/ops/health/`: the four `heartbeats` rows should be fresh (a
   `process_outbox` age above ~180s means beat or the worker is not running), and
   `queues` should not be growing.
5. Send a test contribution through staging and confirm the notification arrives
   and the ledger posts.

### 2. Production

Same sync, then the same two M-Pesa secrets on `wepl-worker`, then the same
`/api/ops/health/` check. Expect a short gap in async processing while
`wepl-api` restarts without its embedded Celery and `wepl-worker` boots — queued
tasks wait in Redis and are picked up, they are not lost.

### If the blueprint sync rejects `plan: starter`

Render has renamed worker instance types over time. Take the current name from
the dashboard's instance-type list and update `plan:` on the four async services.
Nothing else about them depends on it.

### Rolling back

Set `RUN_EMBEDDED_CELERY=true` on `wepl-api` and **suspend `wepl-beat`** (in that
order — never both scheduling at once). The web service returns to the old
layout. `wepl-worker` may stay up; duplicate workers are harmless.

## Watching it after the split

The worker and beat services have no HTTP surface, so there is no health-check
path for Render to poll. Liveness evidence is the DB-backed `WorkerHeartbeat`,
which each watched beat task stamps on completion via a `task_postrun` signal
(`apps/core/apps.py` → `apps/core/health.py`):

- `GET /api/ops/health/` — heartbeats, queue depths and the outbox summary.
- `ops_alerts` (every 5 min) raises a `StaffNotice` bell item on staleness.
- `python manage.py check_workers` — the same rows from a shell, exiting non-zero
  when a task has gone quiet, so it can back an external monitor. `--json` for
  machine consumption.

`process_outbox` is the sharpest signal: it is scheduled every 10 seconds and
only stamps when beat *and* a worker are both alive.

## Guards

`apps/core/tests_deploy_topology.py` reads `render.yaml` and the entrypoint
scripts and asserts them against the Celery settings, because every failure mode
the split introduces is silent — work simply stops happening, or happens twice.
It fails the build if:

- a queue in `CELERY_TASK_ROUTES` has no worker consuming it (or a worker
  consumes a queue nothing routes to);
- a `CELERY_BEAT_SCHEDULE` entry dispatches to a queue no worker serves;
- `start.sh` launches Celery outside the `RUN_EMBEDDED_CELERY` guard, or a web
  service in the blueprint enables that fallback;
- a beat service is not pinned to one instance;
- an async service migrates, skips the migration wait, generates its own
  `SECRET_KEY`, points at a different broker, sits on a `free` plan, or omits
  `ALLOWED_HOSTS` / `DJANGO_SETTINGS_MODULE`;
- a task watched for staleness is not actually in the beat schedule.
