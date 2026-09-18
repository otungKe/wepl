#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# The backend's static checks — everything CI enforces before it runs the
# suite. There is no Python linter in this project; these two checks are its
# equivalent, so run this before pushing.
#
#   backend/scripts/preflight.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

cd "$(dirname "$0")/.."

echo "[preflight] P0-07 legacy-ledger guard..."
scripts/check_legacy_ledger.sh

echo "[preflight] Model/migration drift..."
python manage.py makemigrations --check --dry-run

echo "[preflight] All static checks passed."
