#!/usr/bin/env bash
#
# Celery BEAT entrypoint — the scheduler, on its own service (#161).
#
# This tier must run as EXACTLY ONE instance (numInstances: 1 in render.yaml,
# and never alongside RUN_EMBEDDED_CELERY=true on the web service). A second
# beat re-fires every entry in CELERY_BEAT_SCHEDULE, and
# execute_due_standing_orders firing twice is a duplicate money movement
# attempt, not just duplicate work.
#
# Beat only enqueues; the worker tier executes. Migrations belong to the web
# deploy (see start.sh), so this only waits for the schema to be current —
# django_celery_beat's DatabaseScheduler reads its tables on startup.
set -e

bash wait-for-migrations.sh

echo "[start-beat] scheduler=django_celery_beat.schedulers:DatabaseScheduler"
exec celery -A config beat -l info \
    --scheduler django_celery_beat.schedulers:DatabaseScheduler
