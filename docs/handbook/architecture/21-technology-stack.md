# Architecture / 21 — Technology Stack

> Every chosen technology and the reason it was chosen — including the ones we
> deliberately did *not* choose. The governing bias, from
> [Principle P-21](../product/03-principles.md), is **boring where it counts**: the
> financial core runs on mature, well-understood technology so it never surprises
> us, and novelty is spent only where it earns genuine product advantage.

---

## The stack at a glance

| Layer | Choice | Version |
|-------|--------|---------|
| Language (backend) | Python | 3.12 (pinned) |
| Web framework | Django | 6.0.5 |
| API | Django REST Framework | 3.17 |
| Auth tokens | djangorestframework-simplejwt | 5.5 |
| API schema | drf-spectacular (OpenAPI) | 0.29 |
| Realtime | Django Channels + channels-redis | 4.3 |
| ASGI server | Daphne | 4.2 |
| Async tasks | Celery + django-celery-beat | 5.6 / 2.9 |
| Database | PostgreSQL on **Neon** | 16 |
| Cache / broker / Channels layer | Redis | 7.x |
| Object storage | S3-compatible (R2/S3) via django-storages + boto3 | 1.14 / 1.34 |
| Money | Python `Decimal` + in-house `Money` value object | — |
| SMS | Africa's Talking (+ console backend) | — |
| Email | Brevo / SMTP | — |
| Push | Firebase (FCM) | — |
| OCR (KYC) | pytesseract (optional binary) | 0.3 |
| Errors/observability | Sentry | 2.29 |
| Admin | Django admin + django-unfold | 0.98 |
| Static files | WhiteNoise | 6.12 |
| Member web | Next.js (React) | — |
| Mobile | Expo / React Native | — |
| Hosting | Render (compute) + Neon (Postgres) | — |

---

## Why each choice

### Backend: Django 6 + DRF
A financial system needs a mature ORM with real transactions, migrations,
constraints, and a deep ecosystem — and a team that can hire into it. Django
provides transactional integrity, a first-class migration system (which the
**ledger's balance-invariant DB trigger** is expressed through), and DRF for a
conventional, well-documented REST surface. It is the archetype of "boring where it
counts": nothing about Django will surprise us at 2 a.m., which is exactly what we
want under the money door. Django 6 (on Python 3.12, pinned so Render cannot drift
from CI) is current and supported.

### PostgreSQL (on Neon)
Postgres is the non-negotiable of the stack. The ledger's correctness rests on
Postgres features that are not optional: **transactions**, **deferred constraint
triggers** (the independent balance re-check at COMMIT), **unique constraints** (the
`idempotency_key`), and strong `NUMERIC` for `Decimal(20,4)`. A store without real
transactions and constraints could not host this ledger. **Neon** (not Render's
Postgres) is chosen for branching (staging = a separate branch) and autosuspend
economics; `production.py` uses `CONN_HEALTH_CHECKS` so autosuspend wake-ups
reconnect transparently, and `dj-database-url` parses the connection string.

### Redis — one technology, three jobs
Redis is the Celery **broker**, the Django **cache**, and the Channels **layer**.
Using one well-understood datastore for all three keeps the operational surface
small. Crucially, **nothing authoritative lives in Redis** — it holds broker
messages, cache entries, and ephemeral channel state, all of which are *rebuildable
or replayable*. That is why a Redis outage degrades the system honestly rather than
corrupting it ([System Architecture §Failure domains](20-system-architecture.md)):
the book of record is in Postgres, never Redis.

### Celery + Beat
The async worker tier. Celery's at-least-once delivery and retry semantics are
exactly what the [outbox](26-eventing-architecture.md) is designed around — the
platform assumes retries and builds idempotency to match, rather than pretending
delivery is exactly-once. Queues are routed by concern (`default, notifications,
payments, financial`) so a flood of notifications cannot starve money work.

### ASGI (Daphne) + Channels
Wepl needs both request/response and long-lived connections (chat, live updates),
so it runs on ASGI end to end. Channels + channels-redis provide WebSocket support
with a Redis-backed layer; Daphne is the ASGI server. Choosing ASGI from the start
avoids a painful later migration from a WSGI-only world.

### SimpleJWT + a session registry
Stateless JWTs for scale, backed by a **session registry** for revocation
([ADR-0010](../../adr/0010-session-registry-and-token-revocation.md)) — because a
purely stateless token you cannot revoke is a liability in a money app. Two
completely separate token regimes for the two populations (**P-12**): customer
SimpleJWT and staff `type:"ops"` JWT.

### Object storage (S3/R2) via django-storages
KYC documents and media go to durable, S3-compatible object storage — **never** the
ephemeral dyno disk (a High-severity audit finding, now closed). Evidence pinned to
storage objects is what makes [versioned `CaseDocument`s](../domain/14-identity-architecture.md)
(**P-11**) durable.

### `Decimal` + in-house `Money`
Money is `Decimal(20,4)` wrapped in a `Money` value object carrying currency
([ADR-0003](../../adr/0003-money-representation.md)). We deliberately did **not**
adopt a heavyweight money library; the value object is small, auditable, and does
exactly what the ledger needs — which for the platform's most sensitive type is
worth more than a dependency.

### Channels of delivery: Africa's Talking, Brevo, Firebase
Multi-channel notification delivery ([ADR-0015](../../adr/0015-multi-channel-notification-delivery.md))
with SMS (Africa's Talking, plus a console backend that routes real OTP codes to
logs in production-console mode), email (Brevo/SMTP), and push (FCM). Each channel
sits behind the notification layer, so adding or swapping one does not ripple into
domain code — the same port discipline as payments and identity.

### OCR: pytesseract, optional
In-house KYC ID OCR via a pure-Python `pytesseract` wrapper
([ADR-0023](../../adr/0023-identity-verification-provider.md)); the `tesseract`
binary is optional and the OCR path **degrades to manual review when absent**. A
nice-to-have that never becomes a hard dependency — honest degradation (**P-16**)
applied to a feature.

### Sentry, WhiteNoise, django-unfold
Sentry for error tracking ([ADR-0020](../../adr/0020-observability-standard.md));
WhiteNoise so the API can serve its own static assets without a separate CDN hop;
django-unfold to make the Django admin a usable internal surface without building
one from scratch.

### Frontends: Next.js (web), Expo/React Native (mobile)
See [Frontend](../frontend/40-frontend-architecture.md) and
[Mobile](../frontend/41-mobile-architecture.md). React across both keeps one mental
model and lets a design system share tokens/primitives; Expo gives OTA updates and
a fast path onto real Android devices, which is where the users are.

---

## What we deliberately rejected

- **A NoSQL / eventually-consistent primary store for money.** Disqualified: no
  transactions, no constraints, no provable trial balance. The ledger *requires*
  ACID.
- **Storing balances as mutable columns for read speed.** Rejected permanently
  (**P-3**, [ADR-0002](../../adr/0002-remove-legacy-ledger-and-mutable-balances.md));
  the `AccountBalance` projection gives fast reads without a second source of truth.
- **A microservices split of the core, now.** Rejected as premature: it would add
  distributed-transaction problems to a domain whose defining property is a single
  atomic money-and-event transaction. The [modular monolith](22-module-boundaries.md)
  keeps that transaction local. Service extraction is a *later* option, along tenant
  or read-heavy seams, not a starting posture.
- **A float-based or ad-hoc money type.** Rejected (**P-4**); float loses money.
- **A heavyweight rules engine for governance.** Rejected; centralized policy code
  ([ADR-0009](../../adr/0009-centralized-authorization-policy.md)) is more
  auditable than a DSL for the scale we're at.

---

## The pinning discipline

Python is pinned to 3.12 via `PYTHON_VERSION` **and** `backend/.python-version` so
that Render cannot drift from CI ([Deploy notes in CLAUDE.md](../../../CLAUDE.md)).
Dependency versions are pinned in `requirements.txt`. In a financial system, a
silent minor-version bump is an un-audited change to the money path; pinning makes
every upgrade a reviewed, deliberate act.

---

*Continue to [Module Boundaries](22-module-boundaries.md).*
