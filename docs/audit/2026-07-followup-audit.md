# WEPL — Follow-up Architectural Audit (verification of remediation)

- **Date:** 2026-07-01
- **Type:** Verification audit. Confirms whether the findings in
  [`2026-06-architecture-audit.md`](2026-06-architecture-audit.md) and
  [`2026-06-platform-hardening-review.md`](../review/2026-06-platform-hardening-review.md)
  were genuinely resolved, whether implementation matches the ADRs (0001–0021), and
  whether remediation introduced regressions.
- **Method:** Read every doc in `/docs`; cross-referenced each ADR against the live tree
  at runtime; ran the full test suite; grepped for residual anti-patterns and inline authz;
  inspected the posting core, policy engine, session auth, RLS policies, and the outbox relay.
- **Evidence posture:** claims below carry file:line references and test results, not
  docstring aspiration.

---

## Executive summary

The platform has **genuinely and substantially improved**. The June audit's central
indictment — three sources of monetary truth with a dormant double-entry core — is
**fully resolved**: the double-entry ledger is now load-bearing, the legacy single-entry
ledger and every mutable balance column are gone, `post_journal()` is the enforced money
chokepoint, and a CI grep-guard prevents regression. The hardening review's seven headline
findings have been addressed in code, not just on paper: a centralized authorization policy
(54 call sites), a session registry with real token revocation, an append-only audit log,
API versioning + OpenAPI, structured logging + health probes, a multi-channel notification
layer with dead-letter, and the two "unbuilt" capabilities (search, files) now exist.

**The test story flipped completely.** The June audit found *"45 errors / 4 failures; default
runner finds 0 tests."* Today: **394 tests, green, `OK (skipped=52)`** in ~227s, with CI
coverage gates (≥90%) on the ledger core *and* on the authz/session/isolation/audit/
observability/notifications/reminders code. `makemigrations --check` is clean.

**Two honest caveats keep this short of the ADRs' own language:**

1. **Multi-tenancy isolation is narrower and softer than ADR-0008 implies.** RLS is applied
   to **only two tables** (`ledger_account`, `ledger_financialtransaction`), and the policy
   is **fail-open when `app.tenant_id` is unset**. Celery tasks do **not** set tenant context
   (WebSockets do). So ADR-0008's "cross-tenant reads impossible regardless of an application
   bug" is **overstated** — the backstop only bites when the tenant var is set, and only on
   the two financial tables. Application-layer scoping is doing the real work everywhere else.

2. **The Activity feed (proposed ADR-0016) was never written or built.** `apps/activity/`
   remains a denormalized string log with a **3-line test stub**. It is the single review
   item that received neither an ADR, an implementation, nor tests.

Neither is a launch-blocker for internal/beta, but both should be stated plainly rather than
counted as "done."

**Verdict:** **READY FOR BETA** (see Phase 9). Production-readiness ≈ **72%**.

---

## Phase 2 — Verification of every previous finding

### Central finding — three sources of truth for money → ✅ FULLY RESOLVED (High)
- **Expected fix:** double-entry core authoritative; delete legacy ledger + mutable balances;
  all money via `post_journal()`.
- **Current implementation / evidence:**
  - `LedgerEntry` appears only in migrations `0001`/`0006` (the create + the removal);
    `apps/ledger/queries.py` is deleted; `apps/ledger/writer.py` survives but is **repurposed**
    to only get-or-create the `FinancialTransaction` orchestration row — no shadow ledger
    (`writer.py:1-64`). Consistent with ADR-0004, not a regression.
  - Mutable columns are gone: `Contribution.current_amount` and `SharesFund.total_pool` are
    now **`SerializerMethodField`s deriving from the ledger** (`contributions/serializers.py:20-21,
    53, 240-247`); migration `0020_remove_contributionaccount_contribution_and_more` drops
    `ContributionAccount`, `ContributionBalance`, `current_amount`, `total_pool`.
  - `post_journal` / `posting_map` are used across every money service
    (`contributions/services/{welfare,rosca,standing_orders,disbursement,contribution,advances}.py`
    and `mpesa/views.py:504-507`).
  - **No** `current_amount = F(...)` / `total_pool = F(...)` / `balance = F('balance')`
    mutations exist outside migrations (grep clean).
  - CI grep-guard active (`.github/workflows/ci.yml:73-77`) banning `LedgerEntry`,
    `write_ledger_entry`, `ledger.queries`, `ContributionAccount`, `ContributionBalance`, and
    the F()-balance patterns.
- **Assessment:** The defining Phase-0 move is real and enforced. This is the biggest single
  improvement in the platform.

### `STAGING_OTP_BYPASS=true` in prod → ✅ FULLY RESOLVED (High)
- `config/settings/production.py:14-16` raises `ImproperlyConfigured` at boot if the bypass is
  set; `render.yaml:42-43` explicitly sets it to `"false"` (so a blueprint re-sync actively
  clears a stray value). Guard intact per CLAUDE.md.

### KYC media on ephemeral dyno disk → ⚠ PARTIALLY RESOLVED (High)
- **Expected fix:** durable object storage (S3/R2) for KYC/avatars.
- **Current:** the seam exists — `production.py` gates an S3/R2 `STORAGES` backend on
  `USE_S3` (`production.py:83-99`), and the `files` app (ADR-0018) is the intended home. **But**
  `render.yaml:138-139` ships `USE_S3="false"`, and ADR-0018 explicitly **defers migrating
  existing consumers** (`users.profile_photo`, KYC images) onto `StoredFile`. So *as deployed*,
  KYC docs still land on the ephemeral dyno disk via `ImageField` unless an operator flips
  `USE_S3` and populates creds.
- **Assessment:** infrastructure ready, not yet load-bearing. Flip `USE_S3` + migrate KYC to
  `files` to close it.

### Tests not green / not CI-enforced → ✅ FULLY RESOLVED (High)
- `Ran 394 tests … OK (skipped=52)`. CI runs the suite under coverage with **two** ≥90% gates
  (`ci.yml:94-107`). The 52 skips are `@skip(_LEGACY)` tests for the deleted legacy paths
  (`contributions/tests.py`, `mpesa/tests.py`) — expected post-cutover, though they're dead
  weight worth pruning.

### In-process event signals (lossy) → ✅ FULLY RESOLVED (High)
- Transactional outbox implemented (ADR-0006): `emit()` writes an `OutboxEvent` in-transaction;
  `process_outbox` claims with `select_for_update(skip_locked=True)`, re-fires `domain_event`,
  retries with backoff, and **dead-letters** after `max_attempts` (`core/tasks.py:36-90`).
  Consumers dedupe on `Notification.event_id`.

### No limits/risk → ✅ RESOLVED for limits/velocity (High); AML deferred
- `enforce_controls` is invoked **inside** `post_journal` for member-facing movements
  (`ledger/posting.py:107-109`), so controls cannot be bypassed by a different code path
  (ADR-0007). AML/sanctions screening is a later phase, not claimed done.

### Money precision mismatch (2dp vs 4dp) → ✅ RESOLVED (High)
- `Money` value object with `Decimal(20,4)` + `ROUND_HALF_EVEN` (`ledger/money.py`,
  `tests_money.py`); legacy 2dp columns deleted rather than migrated (ADR-0002/0003).

### God modules → ✅ RESOLVED (High)
- `contributions/services.py` (1,936) → a package of 8 modules, largest 306 lines
  (`services/contribution.py`); `contributions/views.py` (1,114) → a package, largest 438
  (`views/core.py`); `users/views.py` (901) → a package (`auth/account/financial/kyc/privacy/
  profile/sessions`). Public import surface preserved (ADR-0013).

### Double-entry core unintegrated → ✅ RESOLVED (High) — now the load-bearing spine.

### Celery folded into web dyno (Medium) → ⚠ NOT VERIFIED / likely still deferred
- Infra-plan item; not re-checked in depth. Worth confirming `render.yaml` gives Celery its
  own service before real load.

---

## Phase 3 — Implementation-quality spot checks

- **Ledger `post_journal` (`posting.py`)** — *Excellent.* Per-currency balance enforcement
  (not just global), amount>0 guard, **race-safe idempotency** (SELECT then `get_or_create`;
  a lost INSERT race returns the winner without double-posting lines), projection updated with
  `F()` atomics inside the same `@transaction.atomic`, controls chokepoint, and a **deferred DB
  trigger** re-checking Σdebit==Σcredit at COMMIT as an independent backstop. Reversal builder
  flips each leg and is idempotent (`reversal-<key>`).
- **Authorization policy (`core/policy.py` + per-app `policies.py`)** — *Strong.* Two-function
  API (`can`/`require`), prefix-routed resolvers, **fail-closed on unknown action / missing
  resolver** (`PolicyConfigurationError`), superuser bypass, declarative rank matrix. Wired at
  54 sites; resolvers registered in `AppConfig.ready()` for communities/contributions/
  conversations. Residual inline checks are legitimate (last-admin *business* rule; a serializer
  display flag), not authz dispersal.
- **Session auth (`users/auth.py:109-136`)** — *Strong.* `SessionJWTAuthentication` rejects any
  `sid` whose `UserSession` is revoked/absent — making **access** tokens revocable (SimpleJWT's
  blind spot), not just refresh. `ROTATE_REFRESH_TOKENS` + `BLACKLIST_AFTER_ROTATION` on;
  logout / sessions list / per-device + "revoke others" endpoints present.
- **Community invariants (`communities/services.py`)** — *Strong.* `transfer_ownership`,
  `leave_community`, `assign_role`, `remove_member` all `select_for_update`-lock the row; last-
  admin demotion/removal refused (`:195, :302`); ownership transfer keeps the former owner as
  admin so a community can never drop below one admin (ADR-0011). Concurrency-correct.
- **Chat (`conversations/`)** — *Good.* Relational `MessageReaction` with a uniqueness
  constraint, `last_read_message_id` high-water-mark, keyset (`before=`) pagination,
  **tenant-scoped** channel group (`groups.group_name(tenant_id, conversation_id)`), and WS
  writes wrapped in `tenant_context`. Presence/backpressure/resume deferred (documented).
- **Files (`files/`)** — *Good v1.* Per-kind type+size allow-lists, sha256 checksum, scan seam
  (SKIPPED when no engine), `TimestampSigner` signed+expiring downloads bound to file id,
  retention purge. **Caveat:** the download token is a **bearer capability** (no per-actor
  check); a leaked URL grants access for the TTL — acceptable for v1 but relevant for KYC docs.
  Content-type is *declared*, not magic-byte verified (documented).
- **Payments (`payments/`)** — *Good, deliberately non-authoritative.* `PaymentIntent`
  aggregate + `PaymentService.resolve` (idempotent), `reconcile_payments` opening deduped
  `ReconciliationDrift` rows over intent↔FT↔ledger legs. Provider-statement leg and
  end-to-end reversals deferred (documented).
- **Notifications (`notifications/`)** — *Good.* Channel strategy (`channels.py`),
  `channels_for` routing matrix, `NotificationDeadLetter` for exhausted retries. Templates/
  i18n/digests deferred.

---

## Phase 4 — ADR compliance

| ADR | Title | Status | Notes |
|---|---|---|---|
| 0001 | Ledger-first double-entry | **Implemented correctly** | Core is the book of record. |
| 0002 | Remove legacy ledger + mutable balances | **Implemented correctly** | Deleted; grep-guarded. |
| 0003 | Money representation | **Implemented correctly** | `Money`, Decimal(20,4). |
| 0004 | `post_journal` single entrypoint | **Implemented correctly** | Enforced + CI guard. |
| 0005 | Payment provider abstraction | **Implemented** | Port/adapter + FakeProvider. |
| 0006 | Transactional outbox | **Implemented correctly** | Relay + dead-letter + dedupe. |
| 0007 | Controls at posting chokepoint | **Implemented correctly** | `enforce_controls` in `post_journal`. |
| 0008 | Multi-tenancy (RLS) | **Partially implemented** | RLS on **2 tables only**; **fail-open** when unset; **Celery sets no tenant context**. See risk C-1. |
| 0009 | Centralized authorization policy | **Implemented correctly** | 54 sites; fail-closed engine. |
| 0010 | Session registry & revocation | **Implemented correctly** | Access-token revocation real. |
| 0011 | Ownership transfer & last-admin | **Implemented correctly** | Locked, invariant-tested. |
| 0012 | Chat scaling | **Implemented** (scoped) | Reactions/HWM/keyset/tenant channels; presence deferred. |
| 0013 | Contributions module split | **Implemented** | Services + views + users/views split; lifecycle state machine deferred. |
| 0014 | Payment aggregate & reconciliation | **Implemented** (scoped) | Aggregate + recon; statement leg & reversals deferred. |
| 0015 | Multi-channel notifications | **Implemented** (scoped) | Channels + DLQ; templates/digests deferred. |
| **0016** | **Activity feed** | **Not written / not implemented** | Proposed in review; absent from `docs/adr/`; `activity/tests.py` is a 3-line stub. |
| 0017 | Search architecture | **Implemented** (scoped) | Permission-filtered FTS; stored indexes deferred. |
| 0018 | File storage pipeline | **Implemented** (scoped) | Pipeline built; **consumer migration deferred** (KYC risk above). |
| 0019 | Append-only audit log | **Implemented correctly** | `save()` refuses updates. |
| 0020 | Observability standard | **Implemented** (scoped) | JSON logs + health/live+ready; metrics/tracing deferred. |
| 0021 | API conventions | **Implemented** (scoped) | Dual-mount `/api` + `/api/v1`, OpenAPI, pagination default; error-envelope & cursor-default deferred. |

**ADR index hygiene:** `docs/adr/README.md` still lists only 0001–0007 and shows 0005/0006/0007
as "Proposed" though they are Accepted/implemented. The index is stale — update it.

---

## Phase 5 — Regressions & drift

- **No functional regressions found** in the paths inspected. The money core, policy engine,
  session auth, and community invariants are concurrency-correct.
- **Minor code-hygiene drift:**
  - `writer.py` retained (repurposed, legitimate) — but the module name now misleads.
  - ~52 `@skip(_LEGACY)` tests are dead weight; prune them.
  - `docs/adr/README.md` index is stale (see above).
- **Over-/under-reach in claims (drift between ADR text and reality):**
  - ADR-0008's "impossible regardless of an application bug" vs. fail-open + 2-table RLS.
  - ADR-0018 shipped a pipeline but nothing routes through it yet (KYC still on `ImageField`).

---

## Phase 6 — Module scores (1–10)

| Module | Score | Justification |
|---|---:|---|
| Ledger | **9** | Load-bearing, per-currency, idempotent, DB-trigger backstop, ≥90% gated. |
| Contributions | **7** | Routes all money via ledger; split into readable modules; lifecycle state machine still deferred. |
| Payments (aggregate) | **6.5** | Aggregate + reconciliation real; not yet authoritative; statement leg/reversals deferred. |
| M-Pesa | **7.5** | Idempotent callbacks, Safaricom-IP gate, tested. |
| Controls | **7.5** | Single-chokepoint enforcement; tested. |
| Authentication | **7.5** | Session registry, access-token revocation, rotation/blacklist. |
| Users | **6.5** | Views split; privacy model good; KYC media not yet durable. |
| Communities | **7** | Ownership/last-admin invariants + tests; slugs/archive/roles deferred. |
| Conversations (chat) | **6.5** | Reactions table, HWM unread, keyset, tenant channels; presence/backpressure deferred. |
| Notifications | **6.5** | Channel strategy + DLQ + dedupe + tests; templates/digests deferred. |
| Core (events/outbox) | **8.5** | Durable outbox, relay, dead-letter. |
| Tenants / Multi-tenancy | **6** | Solid RLS *on 2 tables*, fail-open, Celery gap. Application-scoping carries the rest. |
| Audit | **7** | Append-only, in-transaction, request-id stamped; not hash-chained; some consumers deferred. |
| Search | **6** | Permission-filtered + ranked v1; query-time FTS won't scale to millions. |
| Files | **6.5** | Validation/scan-seam/signed-URL/retention; bearer-URL + no consumer migration. |
| Reminders | **5.5** | Idempotent-dispatch test present; distributed-lock hardening light. |
| Activity | **3.5** | Unchanged string log, no ADR, 3-line test stub. |
| API layer | **7** | Versioned URL space + OpenAPI + pagination default; error envelope deferred. |
| Observability | **6.5** | Structured logs + correct liveness/readiness split; metrics/tracing deferred. |
| Database/migrations | **8** | Clean `makemigrations --check`; constraints/indexes present; deferred balance trigger. |
| Testing | **7.5** | 394 green + CI coverage gates; concurrency/property tests still thin; activity untested. |
| Documentation (ADRs) | **8** | Excellent ADR discipline; index stale + ADR-0016 missing. |

---

## Phase 7 — Production-readiness ratings (/10)

| Dimension | Score | Justification |
|---|---:|---|
| Security | **7** | Real authz layer, token revocation, OTP-bypass guard, signed uploads. Watch: RLS fail-open, bearer file URLs, KYC durability. |
| Scalability | **6** | Keyset chat, outbox fan-out, cursor paginator exist; query-time search + read-fanout are current ceilings. |
| Reliability | **7** | Durable outbox + DLQ, idempotent money paths, reconciliation. |
| Maintainability | **8** | God modules dissolved; policy centralized; ADRs thorough. |
| Observability | **6.5** | Structured logs + health probes; no metrics/tracing/dashboards yet. |
| Performance | **6.5** | Ledger reads projected/indexed; N+1 audit not exhaustive; no query-plan/caching program. |
| Data integrity | **9** | Double-entry + DB trigger + idempotency + append-only audit. Strongest dimension. |
| Developer experience | **8** | Clear seams, tests green, one money door. |
| Operational readiness | **6** | Health probes + reconciliation; missing metrics/alerting maturity, Celery service split unverified. |
| Disaster recovery | **5.5** | Ledger replayable + rebuildable projection + reconciliation; no documented backup/restore/RTO-RPO drill. |
| Overall architecture | **7.5** | Coherent ledger-first design; remediation matches intent with two honest caveats. |

---

## Phase 8 — Remaining work

### Critical
- **C-1 — Multi-tenancy backstop is narrower/softer than documented.**
  *Risk:* cross-tenant read/write if any code path forgets to set `app.tenant_id`; RLS covers
  only `ledger_account`/`ledger_financialtransaction` and is fail-open when unset; **Celery
  tasks set no tenant context**. *Recommendation:* extend RLS to the other tenant-scoped tables
  (`communities_community`, contributions funds, `controls_*`); set `tenant_context` at the
  Celery task boundary (a `task_prerun`/base task); add a test proving a context-less query is
  denied for a chosen table (or explicitly document fail-open + which ops are platform-wide by
  design). *Effort:* M (3–5 d). *Priority:* Critical (before any real second tenant).
- **C-2 — KYC/media not durable as deployed.** *Risk:* KYC docs + avatars on ephemeral disk are
  lost on redeploy (compliance + UX). *Recommendation:* set `USE_S3=true` with R2/S3 creds and
  migrate KYC/avatar writes onto `files.StoredFile`. *Effort:* M. *Priority:* Critical before beta with real KYC.

### High
- **H-1 — Contribution lifecycle state machine** (ADR-0013 deferred half): enforce status edges
  + DB check constraint. *Risk:* implicit transitions across call sites. *Effort:* M. 
- **H-2 — Payment reversals end-to-end + provider-statement reconciliation** (ADR-0014 deferred).
  *Risk:* no true three-way match; refunds not first-class. *Effort:* M–L.
- **H-3 — Observability metrics + alerting** (ADR-0020 deferred): Prometheus RED/queue-depth/
  outbox-lag/payment-success + `/metrics`. *Risk:* blind in first incident. *Effort:* M.
- **H-4 — Real AV + magic-byte sniffing** in the files scan seam. *Effort:* M.

### Medium
- **M-1 — Activity feed (ADR-0016) — write it and build it**: typed events, visibility rules,
  fan-out decision, tests. *Effort:* M. 
- **M-2 — Stored `SearchVector`/GIN indexes** (ADR-0017 v1.5) before search hits scale. *Effort:* S–M.
- **M-3 — Chat presence / backpressure / resume-from-cursor** (ADR-0012 deferred). *Effort:* M.
- **M-4 — Notification templates + i18n + digests** (ADR-0015 deferred). *Effort:* M.
- **M-5 — Reminders distributed lock** for multi-beat/worker safety. *Effort:* S.
- **M-6 — Audit hash-chaining** if compliance needs tamper-evidence; wire deferred consumers (KYC, votes). *Effort:* S–M.

### Low
- **L-1 — Prune `@skip(_LEGACY)` tests.** *Effort:* S.
- **L-2 — Refresh `docs/adr/README.md`** index (0008–0021 + statuses). *Effort:* S.
- **L-3 — Rename/retire `ledger/writer.py`** to reflect its FT-only role. *Effort:* S.
- **L-4 — Standard error envelope + cursor-pagination default** behind `/api/v2` (ADR-0021 deferred). *Effort:* M.
- **L-5 — Per-actor check (not just bearer token) on sensitive file downloads (KYC).** *Effort:* S.

---

## Phase 9 — Executive summary (scorecard)

1. **Original issues found:** ~10 top risks (June audit) + 7 platform-level findings + 13 per-app
   gaps (hardening review).
2. **Fully resolved:** triple source of truth; dormant core; OTP-bypass-in-prod; lossy events;
   money-precision; god modules; tests-not-green; limits absent; authorization dispersal;
   token revocation/session registry; community ownership/last-admin; audit trail; API
   versioning/OpenAPI; chat data-model ceilings; notifications channel/DLQ.
3. **Partially resolved:** multi-tenancy isolation (RLS narrow + fail-open + Celery gap); KYC
   media durability (seam built, not wired); search (v1, not scale-grade); files (pipeline
   built, consumers not migrated); observability (logs/health, no metrics/tracing); payments
   (aggregate + recon, no statement leg/reversals).
4. **Unresolved:** Activity feed / ADR-0016 (no ADR, no build, no tests); contribution lifecycle
   state machine; AML/sanctions; DR runbook/backups.
5. **Regressions introduced:** none functional. Minor hygiene only (stale ADR index, dead skipped
   tests, misnamed `writer.py`).
6. **New findings:** RLS fail-open + 2-table scope vs ADR-0008 language (C-1); bearer-token file
   downloads for KYC (L-5); `USE_S3=false` in `render.yaml` leaves KYC on ephemeral disk (C-2).
7. **Biggest architectural improvements:** the ledger became the real, enforced book of record;
   authorization became a system instead of a habit; durable eventing + audit + session
   revocation turned "demo-grade" into "operable."
8. **Biggest remaining risks:** multi-tenant isolation gap (C-1) and KYC/media durability (C-2);
   observability blind spots for incident response.
9. **Estimated production readiness:** **≈ 72%.**
10. **Final verdict:** **READY FOR BETA.** The money core is production-grade / near
    enterprise-grade on data integrity; the platform periphery is solid but has two Critical
    items (tenant isolation hardening, media durability) that must close before *limited
    production* with multiple real tenants and real KYC.

---

*This audit did not modify application code; it verifies and records. Each remaining item in
Phase 8 is a self-contained, testable follow-up in the established ADR/PR style.*

---

## Correction (2026-07-12) — a legacy artifact the "legacy wiped" claim missed

The Phase-0 verification confirmed ADR-0002's enumerated legacy (the single-entry
`LedgerEntry` + `writer.py` shadow + `queries.py`, and the mutable balance columns
`current_amount` / `WelfareFund.balance` / `SharesFund.total_pool` /
`ContributionAccount` / `ContributionBalance`) was genuinely gone. It **missed a
different legacy artifact not on that list and not covered by the CI grep-guard**:
`payments.Payment` — a contribution-coupled money record with pre-ADR-0003 precision
(`Decimal(12,2)`) and a mutable `status`, living **outside the ledger**. It was dead
(no writers since manual recording was removed; only a read-only legacy list view +
serializer referenced it) but never deleted, so it survived the cutover.

**Resolved:** the model, its `PaymentSerializer`, the read-only
`ContributionPaymentsView` + its `/api/payments/contribution/<id>/` route, and the
`payments/` URL include were removed, and migration
`payments.0005_delete_legacy_payment` drops the table (consistent with ADR-0002's
clean-reset posture; no client consumed the endpoint). `PaymentIntent` and
`ReconciliationDrift` (the current ADR-0014 code) are unaffected.
