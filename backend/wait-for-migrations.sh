#!/usr/bin/env bash
#
# Block until the database schema is fully migrated, then return.
#
# The async services (start-worker.sh / start-beat.sh) deliberately do NOT run
# migrations themselves: the web service is the single migration writer, and
# three services racing `migrate` on the same database contend on the same
# locks. On a simultaneous deploy the worker can therefore boot against a
# half-migrated schema — beat's DatabaseScheduler in particular reads
# django_celery_beat tables on startup — so it waits here instead.
#
# `migrate --check` exits non-zero while unapplied migrations remain (and also
# while the database is unreachable), which is exactly the condition to keep
# waiting on, so this polls it rather than sleeping a fixed amount.
set -u

DEADLINE="${MIGRATION_WAIT_SECONDS:-300}"
INTERVAL="${MIGRATION_WAIT_INTERVAL:-5}"
waited=0

while [ "$waited" -lt "$DEADLINE" ]; do
    if python manage.py migrate --check >/dev/null 2>&1; then
        echo "[wait-for-migrations] schema up to date after ${waited}s"
        exit 0
    fi
    echo "[wait-for-migrations] waiting for the web deploy to finish migrating (${waited}s/${DEADLINE}s)"
    sleep "$INTERVAL"
    waited=$((waited + INTERVAL))
done

# Don't hard-fail: a long wait is more likely a slow deploy than a broken one,
# and Celery's own connection retry plus the platform's restart-on-crash handle
# the remainder. Starting loudly beats exiting silently.
echo "[wait-for-migrations] WARNING: schema still not up to date after ${DEADLINE}s — starting anyway" >&2
exit 0
