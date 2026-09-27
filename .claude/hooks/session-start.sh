#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# WEPL — SessionStart hook for Claude Code on the web
#
# Brings up everything the Django backend needs to run migrations, the test
# suite, and the dev server inside an ephemeral remote container:
#   1. PostgreSQL 16 (native cluster) + the `wepl` role/database
#   2. Redis 7 (channels / cache / celery broker)
#   3. A Python 3.12 virtualenv with backend requirements installed
#   4. Session env vars (DJANGO_SETTINGS_MODULE, SECRET_KEY, DB_*, REDIS_URL)
#   5. Applied database migrations
#
# Backend requirements plus `coverage`, so a session can reproduce CI's
# coverage gates as well as the plain suite.
#
# Idempotent and non-interactive — safe to run on every session start.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# Only run inside Claude Code on the web (remote) environments.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

REPO="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}"
BACKEND="$REPO/backend"
VENV="$HOME/.venvs/wepl"

# Dev-only values. NOT for production — this key never protects real data.
DEV_SECRET_KEY="dev-insecure-session-start-key-do-not-use-in-production"

echo "[session-start] Preparing WEPL backend environment..."

# ── 1. PostgreSQL 16 ─────────────────────────────────────────────────────────
if ! pg_isready -q -h 127.0.0.1 -p 5432; then
  echo "[session-start] Starting PostgreSQL 16 cluster..."
  pg_ctlcluster 16 main start || true
  for _ in $(seq 1 30); do
    pg_isready -q -h 127.0.0.1 -p 5432 && break
    sleep 1
  done
fi

# Role + database matching backend dev defaults (idempotent).
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='wepl'" | grep -q 1; then
  echo "[session-start] Creating 'wepl' role..."
  sudo -u postgres psql -c "CREATE ROLE wepl LOGIN PASSWORD 'password' SUPERUSER CREATEDB;"
fi
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='wepl'" | grep -q 1; then
  echo "[session-start] Creating 'wepl' database..."
  sudo -u postgres createdb -O wepl wepl
fi

# ── 2. Redis ─────────────────────────────────────────────────────────────────
if ! redis-cli ping >/dev/null 2>&1; then
  echo "[session-start] Starting Redis..."
  redis-server --daemonize yes >/dev/null
fi

# ── 3. Python 3.12 virtualenv + dependencies ─────────────────────────────────
if [ ! -x "$VENV/bin/python" ]; then
  echo "[session-start] Creating Python 3.12 virtualenv at $VENV..."
  python3.12 -m venv "$VENV"
fi
# --timeout/--retries: the remote container reaches PyPI through an egress proxy
# and a bare `pip install` intermittently dies on a read timeout mid-download,
# which (under `set -e`) would abort the hook before migrations ever run.
PIP_NET_OPTS=(--timeout 60 --retries 5)

echo "[session-start] Installing backend requirements..."
"$VENV/bin/pip" install --quiet "${PIP_NET_OPTS[@]}" --upgrade pip
# `coverage` is not a runtime dependency, so it is deliberately absent from
# requirements.txt — but CI runs the suite under it and gates two >=90%
# thresholds on the result, so a session needs it to reproduce a CI failure.
"$VENV/bin/pip" install --quiet "${PIP_NET_OPTS[@]}" -r "$BACKEND/requirements.txt" coverage

# ── 4. Persist environment variables for the session ─────────────────────────
# The hook fires again on resume/clear/compact, so only write these once per
# session env file rather than appending a duplicate block each time.
if [ -n "${CLAUDE_ENV_FILE:-}" ] && ! grep -q '^export DB_NAME=wepl$' "$CLAUDE_ENV_FILE" 2>/dev/null; then
  {
    echo "export PATH=\"$VENV/bin:\$PATH\""
    echo "export DJANGO_SETTINGS_MODULE=config.settings.development"
    echo "export SECRET_KEY=\"$DEV_SECRET_KEY\""
    echo "export DB_NAME=wepl"
    echo "export DB_USER=wepl"
    echo "export DB_PASSWORD=password"
    echo "export DB_HOST=127.0.0.1"
    echo "export DB_PORT=5432"
    echo "export REDIS_URL=redis://127.0.0.1:6379/0"
    echo "export PYTHONUNBUFFERED=1"
  } >> "$CLAUDE_ENV_FILE"
fi

# ── 5. Apply migrations ──────────────────────────────────────────────────────
export PATH="$VENV/bin:$PATH"
export DJANGO_SETTINGS_MODULE=config.settings.development
export SECRET_KEY="$DEV_SECRET_KEY"
export DB_NAME=wepl DB_USER=wepl DB_PASSWORD=password DB_HOST=127.0.0.1 DB_PORT=5432
export REDIS_URL=redis://127.0.0.1:6379/0

echo "[session-start] Applying database migrations..."
( cd "$BACKEND" && python manage.py migrate --noinput )

echo "[session-start] Environment ready."
echo "[session-start]   static checks : backend/scripts/preflight.sh"
echo "[session-start]   test suite    : (cd backend && python manage.py test)"
echo "[session-start]   coverage gates: (cd backend && coverage run --source=apps manage.py test)"
