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

KYC identity checks (the Tier-0 → Tier-1 gate, ADR-0022) run through the
`IdentityVerificationProvider` port in `apps/users/identity/` (`ManualProvider` = human
review, `FakeProvider` = tests, resolved via `registry.get_provider()`, mirrors the payments
port). `KYCEmailVerifyView` calls it via `_run_identity_check()`; a real vendor / IPRS lookup
drops in as another adapter without touching the view (ADR-0023).

**Identity is a ledger too (`apps/verification/`).** Every KYC journey has a `VerificationCase`
whose immutable `CaseEvent` timeline is the source of truth; `KYCProfile.status` is a projection.
All review decisions (ops console, Django-admin actions/form, automated provider outcomes) go
through `apps.verification.service.decide()` — the identity analogue of `post_journal()` —
which enforces the declared transition table and appends the event. Documents are versioned
`CaseDocument` rows pinned to their storage objects; a re-submission adds a version and never
overwrites the evidence a prior decision was made against. Don't mutate case/KYC review state
outside the service.

**Back Office staff are a separate identity from customers.** `apps/backoffice` powers the
operations console at `/api/ops/*`: operators are `StaffAccount` rows (corporate **email +
password**, admin-provisioned, `must_change_password`, no self-serve reset) — *not* customer
`User`s (phone+OTP). They authenticate with a dedicated staff JWT (`apps/backoffice/auth.py`,
`type: "ops"`, separate from customer SimpleJWT). RBAC is a code-defined capability map
(`capabilities.py`) over `ops:*` Django Groups, enforced server-side via `RequireCapability`;
every ops action writes an `AuditEvent` via `record_action()`. The console frontend is a
separate app/deployment — never co-hosted with the customer web app.

## Layout & conventions

- `backend/config/settings/`: `base.py` → `development.py` / `production.py`.
- `backend/apps/`: `ledger` (the book of record), `core` (event bus + outbox), `payments` +
  `mpesa` (rails), `users` (phone auth/KYC), `contributions` (contributions, welfare funds,
  shares, and advances all live here), and `communities`, `conversations`, `notifications`,
  `reminders`, `activity`.
- Async stack: Celery + Beat over Redis, queues `default,notifications,payments,financial`;
  served over ASGI (Channels/Daphne).
- Work items are tracked as `P{phase}-{nn}` (e.g. `P0-05`) and referenced in commit messages,
  phase docs, and GitHub issues — **but never in code**. Code comments/docstrings describe what
  the code does and why it must be so, never what changed or by which PR/work-item/phase/audit
  finding; that history lives in git and the ADRs. References to a governing decision (`ADR-0008`)
  are fine. A CI guard enforces this. See the handbook coding standards.
- The architectural handbook is the reference blueprint: `docs/handbook/` (start at its README;
  new engineers read `docs/handbook/GETTING-STARTED.md`). Decisions are ADRs in `docs/adr/`;
  the convergence plan (moving code onto the handbook) is `docs/handbook/program/61-convergence-plan.md`.

## Deploy

Render via `render.yaml` (blueprint). Note a blueprint sync does **not** delete env vars already
set directly on a service. Python is pinned to 3.12 (`PYTHON_VERSION` + `backend/.python-version`)
so Render doesn't drift from CI.

Postgres is on **Neon**, not Render: each API service carries a `DATABASE_URL` (Neon direct,
non-pooled connection string with `sslmode=require`) set directly on the service in the Render
dashboard. `production.py` prefers `DATABASE_URL` (parsed via `dj-database-url`, with
`CONN_HEALTH_CHECKS` so Neon autosuspend wake-ups reconnect transparently) and falls back to
discrete `DB_*` vars. Staging uses a separate Neon branch/database.
