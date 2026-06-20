#!/usr/bin/env bash
set -e

python manage.py migrate --noinput

# NOTE: Celery worker + beat run in the background of the web process. This is a
# deliberate single-host arrangement for now (Render's free tier has no worker
# plan, and the deployment platform is not yet fixed). Splitting them into
# dedicated worker/beat processes remains the target — see P0-01 in
# docs/roadmap/PHASE-0-ledger-cutover.md — and is independent of any one platform.
celery -A config worker -l info -Q default,notifications,payments,financial --concurrency 2 &
celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler &

# Run Daphne in foreground (keeps the container alive)
exec daphne -b 0.0.0.0 -p "$PORT" config.asgi:application
