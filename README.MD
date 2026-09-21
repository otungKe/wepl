# WEPL

Community finance over M-Pesa — contributions, ROSCA payouts, welfare funds,
emergency advances and shares — built on a ledger-first backend.

The double-entry ledger in `backend/apps/ledger/` is the single source of monetary
truth. `post_journal()` is the only sanctioned way money moves; balances are derived
from immutable journal lines rather than stored in counters, and CI enforces both.

## Layout

| Path | What lives there |
|---|---|
| `backend/` | Django 6 API (Python 3.12), Celery over Redis, ASGI via Daphne. Nearly all work happens here. |
| `mobile/` | Expo / React Native client. |
| `web/` | Customer web app. |
| `backoffice/` | Operations console frontend (separate deployment, never co-hosted with the customer web app). |
| `docs/adr/` | Architecture decision records — start at [`docs/adr/README.md`](docs/adr/README.md). |
| `docs/roadmap/` | Phase-by-phase roadmap — start at [`docs/roadmap/README.md`](docs/roadmap/README.md). |

[`CLAUDE.md`](CLAUDE.md) is the orientation document: the money rule, the eventing
and payment ports, auth, and the conventions this repo is held to.

## Running it

The whole stack (Postgres, Redis, API, Celery worker + beat):

```bash
docker-compose up          # backend on :8000
```

Backend commands run from `backend/` and default to `config.settings.development`:

```bash
python manage.py migrate
python manage.py test                # full suite; needs a live Postgres + Redis
python manage.py test apps.ledger    # one app
python manage.py seed_coa            # seed the chart of accounts
python manage.py reconcile_ledger    # verify the trial balance is zero
```

## Deploy

Render via `render.yaml`, with Postgres on Neon (each service carries its own
`DATABASE_URL`). Deployment notes are in [`docs/deploy/`](docs/deploy/).
