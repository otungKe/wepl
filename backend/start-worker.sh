#!/usr/bin/env bash
#
# Celery WORKER entrypoint — its own service, separate from the web tier (#161).
#
# Why this is not the web process any more: an async burst (notification fan-out,
# hourly payment reconciliation) used to compete with HTTP requests for the same
# CPU, and every web restart killed in-flight tasks. On its own tier the queue
# isolation declared in CELERY_TASK_ROUTES (default / notifications / payments /
# financial) finally buys something — this tier scales on queue depth while the
# web tier scales on request rate.
#
# This service runs no migrations and no provisioning commands; those belong to
# the web deploy (see start.sh). It only waits for the schema to be current.
set -e

# Every queue in CELERY_TASK_ROUTES plus the default queue. A queue that no
# worker consumes is a task that never runs, so this list is asserted against
# the routing table by apps.core.tests_deploy_topology.
QUEUES="${CELERY_QUEUES:-default,notifications,payments,financial}"
CONCURRENCY="${CELERY_CONCURRENCY:-2}"

bash wait-for-migrations.sh

echo "[start-worker] queues=${QUEUES} concurrency=${CONCURRENCY}"
exec celery -A config worker -l info -Q "$QUEUES" --concurrency "$CONCURRENCY"
