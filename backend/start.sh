#!/usr/bin/env bash
#
# WEB entrypoint — release steps, then serve ASGI traffic. Celery does not run
# here: the worker and beat tiers are their own services (start-worker.sh /
# start-beat.sh), so an async burst cannot raise request latency and a web
# restart cannot disrupt in-flight tasks. See #161 / P0-01 and
# docs/deploy/worker-tier.md.
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

# ── Single-host fallback ────────────────────────────────────────────────────
# Runs the async tier inside this process, the way the whole stack used to work
# before #161. It exists for hosts with no worker tier at all (and for a
# temporary rollback), and it is OFF unless explicitly switched on.
#
# Never enable it while the dedicated wepl-worker / wepl-beat services are
# deployed: two beats double-fire every scheduled task, and
# execute_due_standing_orders firing twice is a duplicate money movement
# attempt. The worker half is harmless to double up; the beat half is not.
if [ "${RUN_EMBEDDED_CELERY:-false}" = "true" ]; then
    echo "[start] WARNING: RUN_EMBEDDED_CELERY=true — running Celery worker + beat" >&2
    echo "[start] WARNING: inside the web process (the pre-#161 single-host layout)." >&2
    echo "[start] WARNING: Async work now competes with HTTP requests, and this MUST" >&2
    echo "[start] WARNING: NOT be on while a dedicated beat service is also running." >&2
    celery -A config worker -l info \
        -Q "${CELERY_QUEUES:-default,notifications,payments,financial}" \
        --concurrency "${CELERY_CONCURRENCY:-2}" &
    celery -A config beat -l info \
        --scheduler django_celery_beat.schedulers:DatabaseScheduler &
fi

# Run Daphne in foreground (keeps the container alive)
exec daphne -b 0.0.0.0 -p "$PORT" config.asgi:application
