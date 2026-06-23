# WEPL Platform Hardening & Architecture Review

**Date:** 2026-06-23
**Scope:** Every backend application outside the Core + Ledger (which set the bar).
**Lens:** Principal/Staff review for a platform that must scale to millions of users,
hundreds of thousands of communities, real-time messaging, and multi-provider /
multi-currency / multi-region money movement.

> **How to read this document.** Depth is *risk-proportional*, not uniform. The
> 23-point framework is applied in full to the high-surface, high-risk apps
> (`users`/auth, `communities`, `contributions`, `conversations`, `payments`+`mpesa`,
> `notifications`) and consolidated for thin apps (`activity`, `reminders`,
> `controls`, `tenants`, `core`). Two requested domains — **Search** and **Files** —
> **do not exist as applications**; that absence is itself a finding (§ Platform Gaps).
> Every claim is grounded in the current tree (file/line references included).

---

## 0. Executive Summary

The **money core is genuinely excellent**: `post_journal()` as the single money door,
per-currency balanced journals, a deferred DB trigger re-checking the balance invariant
at COMMIT, the transactional outbox, controls at the posting chokepoint, RLS-based
multi-tenancy, and ≥90% enforced coverage on the ledger core. ADRs 0001–0008 document
the rationale. This is Stripe/Revolut-grade.

**The rest of the platform has not kept pace.** The dominant problem is *not* the money
flows — it is everything around them: **authorization is scattered as inline role checks**,
**several core domains have effectively zero tests**, **the API layer lacks the
conventions a public API needs** (pagination, versioning, schema, consistent errors),
**there is no audit trail outside the ledger**, and **two whole capability areas (search,
files) are unbuilt**. Individually survivable; collectively they are the gap between
"works in a demo" and "operable at scale."

### Platform-wide production-readiness scorecard

| Application | Domain richness | Tests | Authz | API | Observability | **Score /10** |
|---|---|---|---|---|---|---|
| ledger (baseline) | ●●●● | ●●●● | ●●● | ●●● | ●●● | **9** |
| core (events/outbox) | ●●●● | ●●● | n/a | n/a | ●●○ | **8** |
| tenants | ●●● | ●●● | ●●● | n/a | ●●○ | **7.5** |
| controls | ●●● | ●●● | ●●○ | n/a | ●●○ | **7** |
| mpesa | ●●● | ●●● | ●●● | ●●○ | ●●○ | **7** |
| users / auth | ●●● | ●●○ | ●●○ | ●●○ | ●●○ | **6** |
| contributions | ●●●● | ●●● | ●○○ | ●●○ | ●○○ | **6** |
| payments | ●○○ | ●○○ | ●●○ | ●○○ | ●○○ | **4.5** |
| notifications | ●●○ | ○○○ | ●●○ | ●●○ | ●○○ | **4.5** |
| communities | ●●○ | ○○○ | ●○○ | ●●○ | ●○○ | **4** |
| conversations (chat) | ●●○ | ○○○ | ●●○ | ●○○ | ●○○ | **4** |
| activity | ●○○ | ○○○ | ●○○ | ●○○ | ●○○ | **3.5** |
| reminders | ●●○ | ○○○ | ●●○ | ●○○ | ●○○ | **3.5** |
| **Search** | — | — | — | — | — | **0 (absent)** |
| **Files** | — | — | — | — | — | **0 (absent)** |

### The seven platform-level findings that matter most

1. **Authorization is not a system, it is a habit.** ~30 inline `role ==`/`created_by ==`/
   `is_staff` checks live inside views and services (`contributions/views.py` alone ≈18).
   There is no policy layer. This is the single biggest correctness *and* security risk:
   every new endpoint re-implements authz by hand, and the failure mode is silent
   over-permission (IDOR). **→ ADR: centralized policy/authorization layer.**

2. **Core domains have no tests.** `communities/tests.py`, `conversations/tests.py`,
   `notifications/tests.py`, `activity/tests.py`, `payments/tests.py` are **3-line stubs**;
   `reminders` has none. Communities and chat — the social spine of the product — are
   completely unverified. No tenant-isolation test exists for chat (a multi-tenant data-leak
   class of bug).

3. **No audit trail outside money.** The ledger is immutable and the outbox is durable, but
   *who changed a community's settings, who removed a member, who reset whose PIN, who
   approved a KYC* is not recorded anywhere queryable. At scale this is a compliance and
   incident-response blocker. **→ ADR: append-only audit log.**

4. **The HTTP API is pre-public-grade.** `REST_FRAMEWORK` (config/settings/base.py:125) sets
   an exception handler + throttles but **no default pagination, no API versioning, no
   OpenAPI schema, no filter/ordering backends**. List endpoints hand-roll pagination
   inconsistently (`contributions` + `payments` only). A client cannot be generated; a
   breaking change cannot be made safely.

5. **God modules.** `contributions/services.py` is **1,936 lines**; `contributions/views.py`
   **1,114**; `users/views.py` **901**. These mix many bounded contexts (savings, ROSCA,
   welfare, shares, advances, amendments, disbursements). They are past the point where one
   person can hold them in their head — exactly the Ledger anti-pattern the core avoided.

6. **Observability stops at Sentry.** No structured/JSON logging, no metrics (RED/USE), no
   health/readiness endpoints, no tracing, no business KPIs. You will be blind during the
   first real incident.

7. **Capability gaps: Search and Files are unbuilt.** Search is ad-hoc `icontains` filtering;
   there is no indexing, ranking, or permission-filtered global search. File handling has no
   storage abstraction, validation pipeline, signed URLs, or virus-scanning seam — uploads
   appear to go straight to `ImageField`/`FileField`.

---

## 1. Cross-Cutting Architecture (read this before the per-app sections)

### 1.1 Authorization — the headline refactor

**Current state.** Coarse gate is consistent and good: `IsActiveSession` on 81 endpoints
(it enforces a valid *active-stage* JWT). But **fine-grained** authz ("is this user an admin
of *this* community", "may this user disburse from *this* pool", "can they see *this*
member's phone") is implemented inline, e.g.:

- `contributions/views.py` — ~18 sites doing `contribution.is_admin`, `created_by ==`, role math.
- `communities/views.py` / `services.py` — `membership.role == 'admin'` repeated.
- `conversations/` — membership checks duplicated across REST view and the WS consumer.

**Why this fails at scale.** Authz logic that lives at call sites is (a) untestable in
isolation, (b) impossible to audit ("show me everything a treasurer can do"), (c) the #1
source of IDOR — the bug is always the endpoint that *forgot* the check. Stripe/GitHub
solve this with a **policy layer**: declarative, centralized, reusable, independently tested.

**Target.** A `apps/core/policy.py` (or per-app `policies.py`) exposing pure predicates:
```python
def can(actor, action: str, resource) -> bool        # raises nothing
def require(actor, action, resource) -> None          # raises PermissionDenied
```
backed by a small role→permission matrix per resource type, plus thin DRF permission
classes that delegate to it (`HasCommunityPermission('community.settings.update')`). Role
checks then **disappear from business logic**. This is the highest-leverage change in the
whole review.

**→ Suggested ADR-0009: Centralized authorization policy layer.**

### 1.2 API conventions

Add to `REST_FRAMEWORK`:
- `DEFAULT_PAGINATION_CLASS` — **cursor pagination** for feeds/messages/notifications
  (offset pagination collapses on large, append-heavy tables); keep page-number only for
  small admin lists. `apps/core/pagination.py` exists but is not wired as the default.
- `DEFAULT_VERSIONING_CLASS` (`URLPathVersioning`, `/api/v1/…`) — you cannot evolve a mobile
  API without it; old app binaries live for years.
- **OpenAPI** via `drf-spectacular` — generated schema + typed clients for web/mobile.
  Today the web/mobile API clients are hand-maintained and drift (we've already fixed several
  drifts this very session).
- `DEFAULT_FILTER_BACKENDS` (`django-filter` + ordering/search) so list endpoints stop
  hand-rolling query params.
- Standardize the error envelope. `core/exceptions.custom_exception_handler` exists — make
  **every** error pass through it with a stable shape `{ "error": {code, message, details} }`.

### 1.3 Auditability

Introduce an append-only `AuditEvent(actor, action, target_type, target_id, tenant,
metadata, created_at)` written via a tiny service (and/or by subscribing to the existing
outbox `domain_event` signal — you already have the eventing spine). Mandatory for:
membership/role changes, ownership transfer, community settings, KYC decisions, PIN
resets, permission grants, money-adjacent admin actions.

### 1.4 Observability

- **Structured JSON logging** with request id + tenant id + actor id in every line.
- **Metrics**: `django-prometheus` (or StatsD) — request RED metrics, Celery queue depth &
  task latency, WS connection count, outbox lag, payment success rate.
- **Health/readiness**: `/health/live` (process) and `/health/ready` (DB + Redis + broker).
- **Tracing**: OpenTelemetry around HTTP → service → DB → Celery for N+1 and latency hunts.

### 1.5 Background jobs

Queues are separated (`default,notifications,payments,financial`) — good. Missing:
**dead-letter handling** (failed tasks vanish after retries), **distributed locks** for
scheduled jobs (`reminders`/reconciliation will double-fire under >1 beat or worker race),
**idempotency** on notification/email sends (at-least-once delivery ⇒ duplicates without a
dedupe key — `notifications` has `event_id`, good; email tasks do not), and **visibility**
(no flower/metrics on queue depth).

### 1.6 WebSockets (chat)

`conversations/consumers.py`: JWT passed as a **query-string** `?token=` (leaks into proxy/
access logs — prefer a subprotocol header or a short-lived ticket), membership re-checked on
connect (good), token-expiry enforced on receive (good). **Missing**: tenant id is absent
from the channel group name (`conv_{id}` — cross-tenant collision risk if IDs ever overlap
across shards), **no presence**, **no backpressure / max in-flight**, **no per-connection
rate limit**, **no structured reconnect/resume** (clients refetch from scratch).

---

## 2. Per-Application Reviews

### 2.1 Authentication (in `users`) — Score 6/10

**Executive summary.** Phone+OTP+PIN with staged JWTs (`otp_verified` → `otp_recovery` →
`active`) is a clean, well-thought state machine; the production OTP-bypass guard is correct
and must stay. But the auth surface is **missing the table stakes of an account system at
scale**: no refresh-token rotation/revocation list, no session/device registry, no security
event log, no MFA seam, and brute-force protection is single-dimensional.

**Architecture.** Stage claim on the JWT is elegant and the right idea. `issue_tokens`
(users/auth.py) mints access+refresh tagged with a stage. **Phone normalization was just
centralized** (this session) — good, keep extending that discipline.

**Domain model.** `User` keys on `phone_number` (no username) — correct for the market.
`is_pin_set`, `is_phone_verified`, `last_seen` present.

**Service layer.** `OTPService`/`PINService`/`UserService` exist and are reasonable. PIN is
`make_password`-hashed (good), lockout via cache counters (`is_locked`/`record_failure`).
But `users/views.py` is **901 lines** — KYC, profile, privacy, financial-summary, account
deletion all crammed in; split into `views/auth.py`, `views/profile.py`, `views/kyc.py`.

**Security review (active attempt).**
- **Refresh tokens are not rotated or revocable.** With SimpleJWT defaults a leaked refresh
  token is valid until expiry with no blacklist. **→ enable rotation + blacklist; add a
  per-user token version to force global logout.**
- **Brute force**: PIN lockout is per-user cache counter; there is **no per-IP / per-device**
  throttle on `pin/login` beyond the anon rate, and lockout state in cache is lost on cache
  flush (fail-open). Move counters to the DB or a durable store; add IP + device dimensions.
- **No security-event log** (login, failed login, new device, PIN reset, lockout). GitHub
  surfaces these to users; you cannot even surface them to support.
- **OTP**: hashed in cache with expiry (good). Confirm constant-time compare and a hard
  per-phone request cap to prevent SMS-bombing (cost + abuse).
- **Timing**: login returns identical errors for unknown-user vs wrong-PIN (good — no
  enumeration).

**Missing production features.** Device management; session listing + remote revoke; MFA
(TOTP/passkeys) seam; SSO/OAuth readiness (social + enterprise SAML/OIDC); email
verification as a first-class flow (KYC has email verify, but account email is secondary);
account-recovery audit.

**Production readiness.** 6/10. Solid bones, missing the account-security periphery.

**→ ADR-0010: Token lifecycle (rotation, revocation, device/session registry).**

---

### 2.2 Users — Score 6/10

**Domain & privacy.** `PrivacyPreferences` (phone/photo/contribution visibility,
discoverable, online-status) is a genuinely good model and more thoughtful than most MVPs.
Profile update + KYC are present.

**Gaps vs the standard.**
- **No blocking, no reporting, no soft-deletion.** `AccountDeletionView` exists — verify it
  is a *soft* deactivation with a grace + anonymization job, not a hard delete that orphans
  ledger/audit rows (financial history must survive user deletion for compliance).
- **No activity/audit history** for the user themselves ("where am I logged in, what changed").
- **Search**: user search is `icontains` (see §Search) — won't scale and ignores privacy
  ranking (a discoverable user vs a private one must rank/filter differently).
- **Avatars** go to a `FileField`/`ImageField` with no validation/resizing/CDN seam (§Files).

**Performance.** Profile/financial-summary endpoints should be checked for N+1 (aggregations
over contributions/transactions per request — cache the financial summary; it's read-heavy
and recomputed every load, per the mobile Reports screen).

**Readiness.** 6/10.

---

### 2.3 Communities — Score 4/10

**Executive summary.** Reasonable model and a real `CommunityService` (389 lines, 8 atomic
blocks), but **zero tests**, **authz inline**, and **ownership is structurally fragile** —
the exact questions you asked ("can ownership ever be lost? can permissions become impossible
to misuse?") currently answer *yes* and *no*.

**Domain model.** `Community`, `CommunityMembership(role)`, `CommunityJoinRequest`. Governance
fields (join_policy, invite/contribution permission, member-list visibility, cooling-off) are
rich — better than expected. 5 constraint groups in Meta (good).

**The ownership problem.** Ownership is `Community.created_by` (a plain FK), and admin status
is `membership.role == 'admin'`. There is:
- **No ownership-transfer flow** (you listed it; it doesn't exist). If the creator deletes
  their account or is removed, the community can be left with **no owner**.
- **No "last admin" invariant** — nothing stops removal/demotion of the final admin, leaving
  a community **unadministrable**. This needs a DB-aware service guard + test.
- **Role is a free string on membership**, not a permission set — so "treasurer" and
  "officer" (you asked for these) have no distinct capabilities; they'd be more inline checks.

**Boundaries / scale.**
- **Slugs**: communities are addressed by integer id; there are **no slugs** (you asked).
  Add an immutable, unique, tenant-scoped slug for shareable URLs and to avoid id enumeration.
- **Discoverability**: `discover` uses `icontains` — fine at thousands, dies at hundreds of
  thousands (§Search). Needs an index + ranking (member count, recency, locality).
- **Archiving vs deletion**: deletion appears hard; add **archive** (soft) state and make
  hard-delete an admin/retention job that first checks for financial history.

**Security.** Member-list-visibility is modeled but must be enforced in the serializer/policy,
not assumed. Join-by-invite-code: ensure codes are high-entropy and rate-limited (invite-code
guessing = unauthorized membership).

**Tests.** None. This is a **P0**: membership lifecycle, last-admin invariant, join-request
approval authz, invite flow, tenant isolation.

**Refactor.** Move all role logic into the policy layer; add `transfer_ownership`,
`archive`, and a `last_admin` guard; add slugs; index discovery.

**Readiness.** 4/10. **→ ADR-0011: Community roles, ownership & lifecycle.**

---

### 2.4 Chat / Conversations — Score 4/10

**Executive summary.** A working real-time chat (REST + Channels consumer) with reactions,
replies, read state, message soft-delete — but **no tests at all**, **scalability ceilings**
in the data model, and **the WS layer is not tenant-isolated**. For "focus heavily on
scalability," this is the app furthest from the target.

**Domain model.** `Conversation`, `Message` (with `reply_to`, `reactions` JSON, soft `deleted`,
`is_edited`), read tracking. 4 constraint groups. Reactions-as-JSON is fine for small rooms
but **unqueryable and write-contended** for large ones (every reaction rewrites the row →
lock contention). For scale, reactions belong in their own table with a unique
`(message, user, emoji)` constraint.

**Scalability ceilings.**
- **Unread counters**: confirm these are not computed by counting rows per conversation per
  request (N+1 across a community). At scale, maintain a per-(user,conversation) counter
  updated on send/read, or a high-water-mark `last_read_message_id` (cheap, exact).
- **Message pagination**: must be **keyset/cursor on `(conversation, id)`**, never offset.
- **Fan-out**: a message in a large community notifies many users — this must be async via the
  outbox, not inline in the request.
- **Search across messages**: absent (§Search).

**WebSocket review.** Auth via query-string token (move off the URL); membership checked on
connect (good); **group name `conv_{id}` lacks tenant scoping**; no presence, no backpressure,
no per-socket rate limit, no resume-from-cursor on reconnect. Redis channel layer assumed —
confirm it's configured for production (in-memory layer silently works in dev and fails across
processes).

**Moderation / pinning / threads / mentions / attachments**: largely absent (you listed all).
Mentions especially need parsing + notification + a `@everyone` permission gate.

**Encryption readiness**: no envelope/seam. Document the threat model decision (server-side
plaintext is fine for v1, but say so in an ADR).

**Tests**: none. **P0**: send/read/edit/delete, reaction integrity, membership authz on both
REST and WS, **cross-tenant isolation**, pagination correctness.

**Readiness.** 4/10. **→ ADR-0012: Chat data model & real-time scaling (reactions table,
read high-water-mark, cursor pagination, tenant-scoped channels).**

---

### 2.5 Contributions — Score 6/10

**Executive summary.** The richest non-ledger domain by far (savings, ROSCA, welfare, shares,
advances, amendments, disbursements) and it **correctly routes money through the ledger** with
17 atomic blocks and idempotency keys — real financial discipline. But it is a **1,936-line
god-service + 1,114-line view module with ~18 inline authz checks**, and the breadth means the
status-machine invariants are implicit rather than enforced.

**Architecture / boundaries.** This is really **five products in one app**. Split into
sub-packages with their own services and a shared posting-map usage: `savings/`, `rosca/`,
`welfare/`, `shares/`, `advances/`. Each has a distinct lifecycle and approval workflow;
co-locating them is why the module is unmaintainable.

**Domain model.** 14 constraint groups (strong). But: are **status transitions enforced**
(a state machine with allowed edges + a DB check constraint on status), or set by assignment
across many call sites? Define the lifecycle explicitly (`draft→active→closed→archived`,
`request→approved/rejected→executed`) and centralize transitions in the service.

**Transactional integrity.** Money paths look correct (post_journal + idempotency). Verify:
- Every state change that *also* moves money is in **one** transaction with the journal post.
- Disbursement/advance approvals are **idempotent under double-submit** (the vote endpoints
  especially — concurrent admin approvals must not double-execute; needs `select_for_update`
  or a unique vote constraint, which the model may already have — test it).
- **Refunds/cancellations/outstanding balances**: ensure these are ledger reversals, never
  mutations.

**Authz.** ~18 inline checks → the policy layer (§1.1) is the fix.

**Performance.** 15 `select_related/prefetch` uses in services — good awareness — but the
participant/transaction list endpoints over large pools need cursor pagination and cached
aggregates (`current_amount` is derived; confirm it's not recomputed by summing all journal
lines on every read — cache or project it).

**Tests.** 560 lines — the second-best in the platform. Extend with concurrency tests on
votes/disbursements and property tests on balance conservation.

**Readiness.** 6/10. **→ ADR-0013: Contribution lifecycle state machine & module split.**

---

### 2.6 Payments + M-Pesa — Score 4.5/10 (payments) / 7/10 (mpesa)

**Executive summary.** The **provider port/adapter (ADR-0005)** is the right architecture and
`mpesa` is solid (553-line view layer, idempotent callbacks, 399 lines of tests incl.
callback tests). But the **`payments` app itself is a 10-line stub** — the abstraction exists
on paper while the orchestration, reconciliation, and lifecycle live inside `mpesa`. That
inversion will hurt the moment a second provider (card/bank) lands.

**What's good (mpesa).** STK push + B2C + callbacks, idempotency keys, Safaricom-IP permission,
normalized results (`CollectionResult`/`PayoutResult`/`CallbackEvent`). Callback handling is
idempotent and tested — the hardest part, done right.

**Gaps.**
- **`payments` has no domain.** There should be a provider-agnostic `Payment` aggregate
  (intent → pending → succeeded/failed/reversed) that `mpesa` *feeds*, so card/bank slot in
  without touching callers. Today money orchestration is M-Pesa-shaped.
- **Reconciliation**: you listed it; there's a `payments/tasks.py` (69 lines) — verify it
  performs a real three-way reconcile (provider statement ↔ payment intents ↔ ledger) with
  alerting on drift, not just status polling.
- **Reversals/settlements**: model explicitly; reversals must be ledger reversals + provider
  refund, transactionally linked.
- **Webhooks**: signature/IP verified for Safaricom; for future providers, build a generic
  **signed-webhook intake** (raw body store, signature verify, dedupe, async process) — the
  mpesa callback pattern generalized.
- **Evidence uploads / receipts**: manual-payment evidence needs the Files pipeline (§Files);
  receipts should be generated artifacts, not ad-hoc.

**Tests.** mpesa good; `payments` is a stub (3 lines).

**Readiness.** payments 4.5, mpesa 7. **→ ADR-0014: Provider-agnostic Payment aggregate &
reconciliation.**

---

### 2.7 Notifications — Score 4.5/10

**Executive summary.** The event-driven spine is right — `Notification.event_id` dedupe over
the outbox is exactly the at-least-once-safe pattern — but **zero tests**, **no channel
abstraction** (in-app only; push/email/SMS/WhatsApp are "readiness" not reality), and **no
templates/localization/digest/dead-letter**.

**What's good.** Outbox-driven generation, idempotent consumers via `event_id`, a preferences
model, `tasks.py` (161 lines) for async delivery.

**Gaps.**
- **One channel.** Introduce a `NotificationChannel` strategy (in-app/push/email/SMS/WhatsApp)
  + a per-user routing matrix from preferences. Today adding push means editing the consumer.
- **Templates + i18n**: messages are string-built; move to versioned templates with locale
  (multi-country is on the roadmap).
- **Delivery reliability**: retries + **dead-letter** for failed sends; per-channel idempotency
  keys; provider-failure backoff.
- **Digests**: batching/quiet-hours/aggregation ("3 people joined") — absent.
- **Fan-out at scale**: a community-wide event must not create N notifications synchronously.

**Tests.** None — **P0** (dedupe, preference routing, fan-out).

**Readiness.** 4.5/10. **→ ADR-0015: Multi-channel notification delivery.**

---

### 2.8 Activity Feed — Score 3.5/10

**Executive summary.** A minimal `Activity(user, type, message, created_at)` table with a
40-line model and 77-line view. Functional, but it's a **denormalized string log**, not a feed
architecture, with no privacy/visibility rules and no fan-out strategy.

**Gaps.** `message` is a pre-rendered string (can't re-render, localize, or change wording
retroactively) — store a typed event + params and render at read time. **No visibility rules**
(who may see whose activity — privacy leak risk). **Fan-out**: decide read-fanout (cheap
writes, expensive reads) vs write-fanout (the reverse) explicitly — at millions of users this
is an architecture decision, not a default. No aggregation, no pagination guarantees, no
recommendation seam.

**Readiness.** 3.5/10. **→ ADR-0016: Activity feed (typed events, visibility, fan-out model).**

---

### 2.9 Reminders — Score 3.5/10

**Executive summary.** Scheduled-reminder model + beat tasks (46 lines). The **scheduling
correctness** is the concern: under more than one beat process or a worker race, reminders
**double-fire** without a distributed lock + idempotency key on dispatch. No tests.

**Gaps.** Distributed lock around the scheduler tick; idempotent dispatch (dedupe per
(reminder, occurrence)); timezone correctness for multi-country; backfill/catch-up policy for
downtime; tests (none).

**Readiness.** 3.5/10.

---

### 2.10 Controls / Tenants / Core (the strong supporting cast)

- **Controls (7/10).** Limit rules + held movements at the posting chokepoint (ADR-0007),
  tenant-scoped, 166 lines of tests. Good. Extend: admin review UI for held movements; metrics
  on block rate; tests for concurrent limit evaluation.
- **Tenants (7.5/10).** RLS-based isolation (ADR-0008), `FORCE ROW LEVEL SECURITY`,
  `tenant_context`, cross-tenant-attempt logging, 263 lines of tests, the production
  non-superuser DB-role check we built. Strong. **Watch:** `tenant_for_user` still resolves to
  the single default tenant — the real per-user mapping (P6-04) is the next step; until then
  RLS is correct but trivial. Ensure **WS and Celery** set tenant context too (REST does via
  the auth class; background jobs and consumers are the gap).
- **Core (8/10).** Event bus + transactional outbox + relay. Excellent. Add: outbox **lag
  metric** and a **dead-letter** for events that fail delivery past N attempts; document the
  ordering guarantee (none — consumers must be commutative/idempotent).

---

## 3. Platform Gaps — requested apps that don't exist

### 3.1 Search (absent) — **build it**
Today: `icontains` filters in `communities.discover` and user search. At scale this is a table
scan and ignores permissions/ranking. Target: a search service abstraction (Postgres FTS with
`tsvector` + GIN indexes as v1; OpenSearch/Meilisearch seam for v2), **permission-filtered at
query time** (never return rows the actor can't see), ranked, and covering users / communities
/ messages / contributions / global. **→ ADR-0017: Search architecture.**

### 3.2 Files (absent) — **build it**
Today: direct `ImageField`/`FileField`. No validation pipeline, no storage abstraction, no
signed URLs, no virus-scan seam, no retention/deletion policy, no CDN. Target: a `files` app
with an upload pipeline (type/size validation → scan hook → S3-compatible storage →
signed-URL access tied to the policy layer → retention job). Avatars, KYC docs, payment
evidence, chat attachments all route through it. **→ ADR-0018: File storage & media pipeline.**

---

## 4. Prioritized Action Plan

**P0 — correctness, security, and the things that bite first (next 2–4 weeks)**
1. **Centralized authorization policy layer** (§1.1) + migrate `contributions`, `communities`,
   `conversations` off inline checks. Ship with policy unit tests. *(ADR-0009)*
2. **Tests for the untested core**: `communities`, `conversations`, `notifications` —
   lifecycle, authz, and **tenant-isolation** tests. Wire CI coverage gate beyond the ledger.
3. **Last-admin & ownership-transfer invariants** for communities (data-loss/lockout class).
4. **Token rotation + revocation + device/session registry** for auth. *(ADR-0010)*
5. **Tenant context in WebSocket + Celery** (close the isolation gap outside REST).

**P1 — operability & API maturity (next 1–2 months)**
6. API conventions: default **cursor pagination**, **versioning** (`/api/v1`), **OpenAPI**
   (drf-spectacular) + generated clients, consistent error envelope, filter backends.
7. **Audit log** (append-only) for membership/role/ownership/KYC/PIN/admin actions. *(ADR + §1.3)*
8. **Observability**: JSON logging, Prometheus metrics, `/health/live` + `/health/ready`,
   outbox-lag + queue-depth + payment-success dashboards.
9. **Split the god modules**: `contributions` into sub-domains with a lifecycle state machine
   *(ADR-0013)*; `users/views.py` and `contributions/views.py` decomposed.
10. **Notifications multi-channel** abstraction + dead-letter + templates. *(ADR-0015)*

**P2 — scale & capability (the next quarter)**
11. **Chat scaling**: reactions table, read high-water-mark, cursor pagination,
    tenant-scoped channels, presence/backpressure. *(ADR-0012)*
12. **Provider-agnostic Payment aggregate** + real reconciliation. *(ADR-0014)*
13. **Search** service *(ADR-0017)* and **Files** pipeline *(ADR-0018)*.
14. **Activity feed** redesign (typed events + fan-out decision) *(ADR-0016)*.
15. **Reminders** distributed locking + idempotent dispatch.

---

## 5. Suggested ADRs (to be written, mirroring docs/adr/ style)

| ADR | Title | Why now |
|---|---|---|
| 0009 | Centralized authorization policy layer | Eliminates ~30 inline checks; closes IDOR class |
| 0010 | Token lifecycle: rotation, revocation, device/session registry | Account-takeover containment |
| 0011 | Community roles, ownership & lifecycle | Prevents orphaned/unadministrable communities |
| 0012 | Chat data model & real-time scaling | Reactions/read/pagination/tenant channels |
| 0013 | Contribution lifecycle state machine & module split | Tames the 1,936-line service |
| 0014 | Provider-agnostic Payment aggregate & reconciliation | Multi-provider readiness |
| 0015 | Multi-channel notification delivery | Push/email/SMS/WhatsApp + DLQ |
| 0016 | Activity feed architecture | Fan-out + visibility at scale |
| 0017 | Search architecture | Permission-filtered, ranked, indexed |
| 0018 | File storage & media pipeline | Validation, signed URLs, virus-scan, CDN |
| 0019 | Append-only audit log | Compliance + incident response |
| 0020 | Observability standard (logs/metrics/health/tracing) | Operate at scale |

---

## 6. Suggested Future Improvements (beyond the plan)

- **Multi-currency UX end-to-end** (the ledger is per-currency-correct; surfaces aren't).
- **Multi-region**: read replicas + tenant→region pinning; the RLS + tenant context already
  give you the seam.
- **Property-based + concurrency testing** as a standard (Hypothesis for balance conservation;
  parallel-vote tests for disbursements).
- **Idempotency-Key HTTP header** convention for all unsafe public mutations (Stripe-style),
  not just internal money ops.
- **Feature flags** for staged rollout of the above.

---

## 7. What this review deliberately did **not** do

It did not refactor code. A review of this breadth must be *accepted and sequenced* before
touching 14 apps — blind refactoring is exactly the recklessness this document argues against.
The Action Plan (§4) is the execution order; each P0 item is a self-contained PR with tests.
**Recommended first PR: ADR-0009 + the policy layer + migrating `communities` authz, with a
full community test suite** — it's the highest leverage and unblocks the rest.
