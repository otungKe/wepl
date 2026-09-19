#!/usr/bin/env bash
#
# WEB entrypoint — release steps, then serve ASGI traffic, plus the Celery
# worker and beat while RUN_EMBEDDED_CELERY is on (it is, by default).
#
# The target is for those two to be their own services — start-worker.sh and
# start-beat.sh, declared in render.worker-tier.yaml — so an async burst cannot
# raise request latency and a web restart cannot disrupt an in-flight task.
# That needs a paid Render worker instance type, so it waits; everything but the
# cost is in place. See #161 / P0-01 and docs/deploy/worker-tier.md.
set -e

# The web service is the single migration writer; the async services wait for
# this to finish rather than racing it (see wait-for-migrations.sh).
python manage.py migrate --noinput

# Provision platform admin on deploy (the free tier has no shell). All are
# idempotent and never fail the boot: seed_admin_roles creates the staff role
# groups; ensure_superuser creates/updates the admin from ADMIN_PHONE /
# ADMIN_PASSWORD env vars (skips quietly if they're unset).
python manage.py seed_admin_roles
python manage.py seed_ops_roles
python manage.py ensure_superuser
python manage.py create_ops_admin

# ── Single-host layout ──────────────────────────────────────────────────────
# Runs the async tier inside this process. This is what is deployed TODAY: the
# dedicated worker + beat services need a paid Render instance type, so they
# wait in render.worker-tier.yaml until that is adopted (#161).
#
# It therefore defaults to ON. A web process that finds itself unconfigured must
# keep doing the async work rather than silently stop doing it — with no worker
# service anywhere, "off" means the outbox never relays, no notification is
# delivered and nothing reconciles, and nothing raises to say so.
#
# At cutover this flips to "false" in render.yaml in the same edit that adds the
# worker services, because the two half-states are both broken: embedded beat
# plus a dedicated beat is two schedulers double-firing every entry in
# CELERY_BEAT_SCHEDULE, and neither one is no async processing at all.
if [ "${RUN_EMBEDDED_CELERY:-true}" = "true" ]; then
    echo "[start] Running Celery worker + beat inside the web process" >&2
    echo "[start] (RUN_EMBEDDED_CELERY is on). Async work shares this dyno's CPU" >&2
    echo "[start] with HTTP requests. Adopt render.worker-tier.yaml to split it." >&2
    celery -A config worker -l info \
        -Q "${CELERY_QUEUES:-default,notifications,payments,financial}" \
        --concurrency "${CELERY_CONCURRENCY:-2}" &
    celery -A config beat -l info \
        --scheduler django_celery_beat.schedulers:DatabaseScheduler &
fi

# Run Daphne in foreground (keeps the container alive)
exec daphne -b 0.0.0.0 -p "$PORT" config.asgi:application
