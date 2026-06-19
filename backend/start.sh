#!/usr/bin/env bash
set -e

# Web dyno entrypoint. Runs DB migrations then the ASGI server ONLY.
#
# Celery worker and beat run as their own Render services (see render.yaml) so a
# crash, restart, or scaling event in one does not take the others down, and the
# web process is never blocked by in-flight payment tasks. Do NOT launch Celery
# from here.
python manage.py migrate --noinput

exec daphne -b 0.0.0.0 -p "$PORT" config.asgi:application
