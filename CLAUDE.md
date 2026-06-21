# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

WEPL is a Django (6.0.5) backend for a community-finance app (contributions, ROSCA payouts,
welfare funds, emergency advances, shares) over M-Pesa, being evolved into a **ledger-first
"Financial OS."** The mobile client lives in `mobile/` (Expo/React Native); nearly all work
happens in `backend/`. Run all backend commands from the `backend/` directory.

The roadmap that governs the architecture's direction lives in `docs/roadmap/` (start with
`docs/roadmap/README.md`); structural decisions are recorded as ADRs in `docs/adr/`. Read
the relevant phase/ADR before changing money flow, eventing, or payment integration — those
documents are the source of truth, mirrored to GitHub epics (#4–#13).

## Commands

Backend (`cd backend`, Python 3.12, settings default to `config.settings.development`):

```bash
python manage.py migrate                      # apply migrations
python manage.py makemigrations --check --dry-run   # CI fails if models drift from migrations
python manage.py test                         # full suite
python manage.py test apps.ledger             # one app
python manage.py test apps.ledger.tests_posting_map.PostingMapTests.test_contribution  # one test
python manage.py seed_coa                      # seed the chart of accounts
python manage.py reconcile_ledger              # verify the ledger balances (trial balance == 0)
```

Test discovery picks up both `tests.py` and `tests_*.py` files. Tests need a live Postgres +
Redis (CI provisions them as services; locally use `docker-compose up db redis`).

Full local stack (web + Celery worker + beat + Postgres + Redis + Daphne):

```bash
docker-compose up           # backend on :8000 (ASGI via Daphne)
```

## Money architecture — the one rule that matters

The double-entry ledger in `apps/ledger/` is the **single source of monetary truth**.
Everything below is enforced; violating it breaks CI.

- **`post_journal()` (`apps/ledger/posting.py`) is the ONLY door money walks through.** It is
  the sole sanctioned way to create `JournalEntry`/`JournalLine` rows. It guarantees atomically:
  Σdebit == Σcredit (≥2 lines), idempotency on `idempotency_key` (safe under Celery retry), and
  a consistent `AccountBalance` projection update. A deferred DB constraint trigger re-checks the
  balance invariant at COMMIT independently.
- **Balances are derived from immutable journal lines**, never stored as mutable counters. There
  are no authoritative balance columns to increment.
- **Never hand-roll journals.** Every money operation has a canonical debit/credit recipe in
  `apps/ledger/posting_map.py` (returns balanced `list[Line]`); services call those builders.
  Account codes live in `apps/ledger/coa.py` (e.g. `1000` M-Pesa Float, `4000` Fee Revenue).
- **Money is `Money`/`Decimal`** (`apps/ledger/money.py`) — never float. See ADR-0003.
- **CI grep-guard (P0-07)** in `.github/workflows/ci.yml` fails the build if legacy single-entry
  ledger code or mutable balance caches are reintroduced (`LedgerEntry`, `ContributionAccount`,
  `current_amount = F(...)`, etc.). Do not bring these back — see ADR-0002. The ledger core
  (`posting.py`, `balances.py`, `coa.py`, `money.py`, `posting_map.py`) is also held to ≥90%
  test coverage in CI.

## Durable eventing (transactional outbox — Phase 2, ADR-0006)

Domain events must never be lost. Services announce events via `emit(...)`
(`apps/core/events.py`), which writes an `OutboxEvent` row **in the current transaction** — so a
rolled-back transaction discards the event and a crash never loses it. The `process_outbox`
relay (`apps/core/tasks.py`) delivers at-least-once by re-firing the `domain_event` signal;
consumers register receivers in their `AppConfig.ready()` and dedupe idempotently via
`Notification.event_id`. `emit()`'s signature is fixed (~30 call sites) and payloads must be
JSON-serialisable primitives (IDs/strings/numbers), never ORM objects.

## Payments (port/adapter — Phase 1, ADR-0005)

Payment rails are abstracted behind the `PaymentProvider` port in `apps/payments/providers/`
(`MpesaProvider`, `FakeProvider`, resolved via `registry.get_provider()`). All Daraja-specific
wire details (STK push, B2C, callback field names) stay inside `apps/payments/providers/mpesa.py`
and `apps/mpesa/`. Code above the provider layer uses normalized results
(`CollectionResult`/`PayoutResult`/`CallbackEvent`/`StatusResult`) and must not import Daraja
field names.

## Auth & the OTP-bypass guard

The custom user model is `users.User` — **`phone_number` is the identifier** (no username);
auth is phone + OTP, JWT via SimpleJWT. `STAGING_OTP_BYPASS` accepts a fixed `000000` OTP for
any phone in dev/staging. **`config/settings/production.py` raises `ImproperlyConfigured` at boot
if `STAGING_OTP_BYPASS` is set while `DEBUG=False`** — this guard is intentional and must not be
weakened. In production, `SMS_BACKEND=console` routes real OTP codes to the logs.

## Layout & conventions

- `backend/config/settings/`: `base.py` → `development.py` / `production.py`.
- `backend/apps/`: `ledger` (the book of record), `core` (event bus + outbox), `payments` +
  `mpesa` (rails), `users` (phone auth/KYC), `contributions` (contributions, welfare funds,
  shares, and advances all live here), and `communities`, `conversations`, `notifications`,
  `reminders`, `activity`.
- Async stack: Celery + Beat over Redis, queues `default,notifications,payments,financial`;
  served over ASGI (Channels/Daphne).
- Work items are tracked as `P{phase}-{nn}` (e.g. `P0-05`) and referenced in commit messages,
  phase docs, and GitHub issues.

## Deploy

Render via `render.yaml` (blueprint). Note a blueprint sync does **not** delete env vars already
set directly on a service. Python is pinned to 3.12 (`PYTHON_VERSION` + `backend/.python-version`)
so Render doesn't drift from CI.
