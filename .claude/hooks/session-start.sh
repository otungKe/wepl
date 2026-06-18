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
echo "[session-start] Installing backend requirements..."
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$BACKEND/requirements.txt"

# ── 4. Persist environment variables for the session ─────────────────────────
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
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
