# The async tier: worker + beat as their own services

**Issue:** [#161](https://github.com/otungKe/wepl/issues/161) · residual P0-01 debt ·
the "current vs target" row in
[Production_Operations_Roadmap.md](../Production_Operations_Roadmap.md).

> **Status: built, guarded, not adopted.** Render has no free instance type for
> `type: worker`, so the two async services would be the first paid services in
> the blueprint. Until that is paid for, Celery still runs inside the web
> process (`RUN_EMBEDDED_CELERY`, on by default) and the service definitions
> wait in [`render.worker-tier.yaml`](../../render.worker-tier.yaml), which
> Render does not read. Nothing in the repository bills anything, and a
> blueprint sync for an unrelated reason cannot accidentally start the cutover.
> [Adopting it](#adopting-it-the-cutover) is one small pull request.

## The problem

`backend/start.sh` launches the Celery worker and beat in the background of the
web container and then execs Daphne. Three processes, one dyno:

- A notification fan-out or the hourly payment reconciliation competed with HTTP
  requests for the same CPU, so an async burst raised request latency.
- Every web deploy or restart killed in-flight tasks.
- The queue isolation in `CELERY_TASK_ROUTES` (`default`, `notifications`,
  `payments`, `financial`) bought nothing, because one process served all four and
  could not be scaled apart from the API.

There is now one entrypoint per tier, ready to use:

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

### The switch, and why it defaults on

`RUN_EMBEDDED_CELERY` decides whether the web process runs Celery itself. It is
**on by default**, because that is the layout actually deployed: with no worker
service anywhere, a web process that defaulted to off would silently stop
relaying the outbox, delivering notifications and reconciling — and nothing
would raise to say so. `render.yaml` declares it `"true"` explicitly rather than
relying on the default, so a re-sync overwrites whatever was set on the service
by hand, the same trick already used for `STAGING_OTP_BYPASS`.

Both half-states are broken, in opposite directions:

| `RUN_EMBEDDED_CELERY` | worker services | result |
|---|---|---|
| `true` | absent | **today.** Async work shares the web dyno. |
| `false` | present | **the target.** Async work on its own tier. |
| `true` | present | two schedulers, double-firing every beat entry. |
| `false` | absent | no async processing at all, silently. |

So the switch and the presence of the worker services have to move in one edit.
`apps/core/tests_deploy_topology.py` fails the build on either of the bottom two
rows, which is what makes the cutover atomic rather than a two-step you can
half-finish.

## Configuration

| Variable | Default | Where |
|---|---|---|
| `CELERY_QUEUES` | `default,notifications,payments,financial` | worker service; set it to shard queues across services |
| `CELERY_CONCURRENCY` | `2` | worker service |
| `MIGRATION_WAIT_SECONDS` | `300` | worker + beat services |
| `RUN_EMBEDDED_CELERY` | `true` | web service; `false` at cutover, and the way back |

Every credential on `wepl-worker` / `wepl-beat` is copied from the API service
with `fromService` / `envVarKey` rather than re-declared, so each secret is still
entered exactly once in the dashboard and the tiers cannot drift apart.

`SECRET_KEY` in particular **must** be the web service's, not a fresh
`generateValue`: signed download URLs (`apps/files/signing.py`) and the
`FIELD_ENCRYPTION_KEYS` fallback derive from it, so a different key on the worker
silently breaks anything the other tier signed or encrypted. A test asserts this.

## Adopting it (the cutover)

Nothing in the repository touches a running service, and nothing here costs
money today. The async services are not in `render.yaml`, so a blueprint sync
cannot create them.

**The prerequisite is a paid worker instance type** — roughly $7/month per
service, so about $14/month for production alone, $28 with staging. That is the
only thing still missing.

### 1. One pull request

1. Paste the service entries from `render.worker-tier.yaml` into `render.yaml`.
2. Flip `RUN_EMBEDDED_CELERY` to `"false"` on `wepl-api` and `wepl-api-staging`.
3. Flip the default in `backend/start.sh` to `false` to match.

The topology tests fail unless all three land together, so CI checks the edit is
coherent before it merges. Do staging alone first if you'd rather: paste only the
`-staging` pair and flip only `wepl-api-staging`.

### 2. Sync, staging first

1. Render dashboard → the `wepl` blueprint → **Sync**. It creates
   `wepl-worker-staging` / `wepl-beat-staging` and sets `RUN_EMBEDDED_CELERY=false`
   on `wepl-api-staging`.
2. Set two secrets **on `wepl-worker-staging`** (the B2C payout call in
   `apps/ledger/tasks.py` runs on this tier now, and these two are not declared
   on the API service to be copied from):
   - `MPESA_B2C_INITIATOR_NAME`
   - `MPESA_B2C_SECURITY_CREDENTIAL`
   Set the same two on `wepl-beat-staging` if a sync asks for them.
3. Watch the worker's log for `[wait-for-migrations] schema up to date`, then
   `celery@… ready`, and beat's `Scheduler: Sending due task process-outbox`.
4. Confirm the tier is consuming, from `GET /api/ops/health/`: the four
   `heartbeats` rows should be fresh (a `process_outbox` age above ~180s means
   beat or the worker is not running) and `queues` should not be growing.
5. Send a test contribution through staging and confirm the notification arrives
   and the ledger posts.

Production is the same, plus the same two secrets on `wepl-worker`. Expect a
short gap in async processing while `wepl-api` restarts without its embedded
Celery and `wepl-worker` boots — queued tasks wait in Redis and are picked up,
they are not lost.

**Pick the moment.** Between the worker services coming up and `wepl-api`
redeploying with the flag off, both may briefly schedule. `process_outbox` and
the reconciliation jobs are idempotent, and `execute_due_standing_orders` takes
`select_for_update(skip_locked=True)`, so a duplicate run skips rather than
double-pays. Still, sync outside the beat schedule's busy minutes — 08:00,
12:00 and 18:00 EAT for standing orders, 02:00, 03:00 and 09:00 for the daily
jobs.

### If the blueprint sync rejects `plan: starter`

Render has renamed worker instance types over time. Take the current name from
the dashboard's instance-type list and update `plan:` on the async services.
Nothing else about them depends on it.

### Rolling back

Set `RUN_EMBEDDED_CELERY=true` on `wepl-api` and **suspend `wepl-beat`** (in that
order — never both scheduling at once). The web service returns to the current
layout. `wepl-worker` may stay up; duplicate workers are harmless.

## Watching it after the cutover

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

`apps/core/tests_deploy_topology.py` reads `render.yaml`,
`render.worker-tier.yaml` and the entrypoint scripts and asserts them against
the Celery settings, because every failure mode the split introduces is silent —
work simply stops happening, or happens twice. It reads the async services from
whichever file currently declares them, so they stay guarded while they wait and
after they move. It fails the build if:

- a queue in `CELERY_TASK_ROUTES` has no worker consuming it (or a worker
  consumes a queue nothing routes to);
- a `CELERY_BEAT_SCHEDULE` entry dispatches to a queue no worker serves;
- `start.sh` launches Celery outside the `RUN_EMBEDDED_CELERY` guard;
- the switch disagrees with the deployed topology in either direction — worker
  services declared while a web service still schedules, or a web service not
  scheduling with no worker service to do it instead;
- a beat service is not pinned to one instance;
- an async service migrates, skips the migration wait, generates its own
  `SECRET_KEY`, points at a different broker, sits on a `free` plan, or omits
  `ALLOWED_HOSTS` / `DJANGO_SETTINGS_MODULE`;
- a task watched for staleness is not actually in the beat schedule.
