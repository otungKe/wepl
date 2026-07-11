# Architecture / 20 — System Architecture

> The runtime shape of Wepl: the processes, the data stores, and how a request and
> a shilling actually flow through the system. This is the *physical* companion to
> the [Domain Model](../domain/10-domain-model.md)'s logical view.

---

## The shape in one diagram

```
   ┌─────────────┐     ┌─────────────┐        ┌──────────────┐
   │ Mobile app  │     │ Member web  │        │  Ops console │   (separate deploy, P-12)
   │ (Expo/RN)   │     │  (Next.js)  │        │  (frontend)  │
   └──────┬──────┘     └──────┬──────┘        └──────┬───────┘
          │  HTTPS / JWT      │                      │  HTTPS / staff JWT
          └───────────┬───────┴──────────────────────┘
                      ▼
          ┌───────────────────────────┐        M-Pesa (Daraja) ─┐
          │   API tier — Django (ASGI │◄── callbacks ───────────┤
          │   via Daphne)             │                         │  rails
          │   • DRF REST + JWT        │── STK / B2C ────────────┘
          │   • Channels (WebSocket)  │
          │   • post_journal() door   │
          └─────┬───────────┬─────────┘
                │ writes     │ emit() (same txn)
                ▼            ▼
       ┌──────────────┐  ┌───────────────┐
       │  PostgreSQL  │  │  OutboxEvent   │   (durable events, in the business txn)
       │  (Neon)      │  │  rows in PG    │
       │  • ledger    │  └───────┬────────┘
       │  • projections│         │ process_outbox relay
       │  • audit/case │         ▼
       └──────────────┘  ┌───────────────────────────────┐
                         │  Celery workers + Beat         │
             Redis ◄─────┤  queues: default, notifications,│
        (broker + cache  │  payments, financial           │
         + Channels layer)│  • outbox delivery             │
                         │  • rail calls / reconciliation  │
                         │  • notifications (SMS/email/push)│
                         └───────────────────────────────┘
                    object storage (S3/R2) ── KYC media, profile photos
                    Sentry ── errors/observability
```

## The processes

| Process | Technology | Responsibility |
|---------|-----------|----------------|
| **API tier** | Django 6 on **ASGI via Daphne** | Serve DRF REST + JWT auth; hold Channels WebSocket endpoints; the *only* place `post_journal()` is called synchronously in-request. |
| **Celery workers** | Celery 5 over Redis | Async work: outbox delivery, rail calls/reconciliation, notifications, reminders. Queue-routed by concern. |
| **Celery Beat** | django-celery-beat | Scheduled work: standing orders, reconciliation (`reconcile_ledger`), reminders. |
| **PostgreSQL** | Neon (managed) | The single durable store of record: ledger, projections, cases, audit, outbox. |
| **Redis** | managed | Celery broker **and** cache **and** Channels layer. |
| **Object storage** | S3-compatible (R2/S3) | KYC documents and media (never on dyno disk — an audit finding, now fixed). |

Served over **ASGI** because Wepl needs both request/response (REST) and
long-lived connections (Channels/WebSocket for chat and live updates,
[ADR-0012](../../adr/0012-chat-scaling.md)) in one coherent stack.

## Two request planes

1. **Customer plane** — mobile + member web → API tier, authenticated with customer
   SimpleJWT. Phone+OTP identities.
2. **Operator plane** — ops console → the same API tier under `/api/ops/*`,
   authenticated with the **staff JWT** (`type:"ops"`), enforced by
   `RequireCapability`. **Separate frontend deployment** (**P-12**); shared backend
   process but rigorously separated auth and authorization.

The planes share a database and a codebase but never share an identity or a token
([Identity Architecture](../domain/14-identity-architecture.md)).

## The money path at runtime (the critical path)

Tracing [User Journey J3](../product/05-user-journeys.md) through the boxes:

1. **Request in** → API tier initiates a **collection** via the `PaymentProvider`
   port → M-Pesa STK push. No journal yet.
2. **Callback in** (async, from Daraja) → normalized to a `CallbackEvent`.
3. **Post** → service calls `post_journal()` with a `posting_map` recipe, inside a
   DB transaction. Idempotency key makes a duplicated callback a no-op. The
   `AccountBalance` projection updates in the same transaction; the DB trigger
   re-checks the balance at COMMIT.
4. **Emit** → `emit()` writes an `OutboxEvent` **in that same transaction** — so the
   event lives or dies with the money movement (**P-9**).
5. **Fan-out** → `process_outbox` (Celery) delivers the event at-least-once;
   consumers notify the member, update the activity feed, etc., idempotently.

The load-bearing property: **steps 3 and 4 are one transaction.** Everything after
is asynchronous and idempotent, so it can be retried freely without risk to the
book of record.

## Synchronous vs asynchronous — the dividing line

- **Synchronous, in-request, in one DB transaction:** money posting
  (`post_journal`), balance projection, event *emission* (the outbox *write*),
  identity decisions (`decide`), audit writes. These must be atomic with the action
  that caused them.
- **Asynchronous, via Celery, idempotent:** event *delivery*, notifications, rail
  calls that can be retried, reconciliation, reminders, feed updates. These may lag
  and may be retried; correctness never depends on their timing.

This line is the single most important operational decision in the system: **truth
is written synchronously; effects are delivered asynchronously and idempotently.**
It is why a broker outage cannot corrupt the ledger — the truth was already
committed to Postgres before Celery was ever involved (request-path hardening,
commits #155–#157).

## Failure domains and blast radius

| If this fails… | …the system | Because |
|----------------|-------------|---------|
| Redis (broker/cache) | keeps serving money truth; delivery/notifications lag; auth degrades **honestly** (`503` for OTP) | truth is in Postgres; the outbox drains when Redis returns (**P-16**) |
| A Celery worker | no lost events | outbox is durable; work is re-driven at-least-once (**P-9**) |
| M-Pesa/Daraja | collections/payouts pause; nothing mis-posts | posting only happens on confirmed callbacks; ambiguity → suspense |
| The API tier | full outage, but no corruption | no half-written journals — the DB trigger forbids unbalanced commits |
| Postgres | hard outage | it is the single store of record; HA/backups are the mitigation (see [Infrastructure](../operations/50-infrastructure.md)) |

The design concentrates *correctness* in one place (Postgres + the ledger
invariants) and makes everything else *degradable*. That is the deliberate shape:
one thing that must never be wrong, and many things that may be temporarily slow.

## Current deployment vs target

Today (`render.yaml`) the stack runs on Render (API as a `web` service, Redis
managed there) with Postgres on **Neon**. On the free plan, Celery has at times
been folded into the web dyno — an audit-flagged compromise. The *target* shape,
and the reason the process table above lists workers separately, is
**independently scaled worker processes**; see
[Infrastructure](../operations/50-infrastructure.md) and
[Scalability](../operations/53-operations-and-scalability.md) for the path from
here to there.

---

*Continue to [Technology Stack](21-technology-stack.md) and
[Module Boundaries](22-module-boundaries.md).*
