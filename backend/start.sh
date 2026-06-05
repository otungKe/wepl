#!/usr/bin/env bash
set -e

python manage.py migrate --noinput

# Run Celery worker and Beat in background
celery -A config worker -l info -Q default,notifications,payments,financial --concurrency 2 &
celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler &

# Run Daphne in foreground (keeps the container alive)
exec daphne -b 0.0.0.0 -p "$PORT" config.asgi:application
