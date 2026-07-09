# Production Operations Roadmap

The ordered build plan that takes WEPL's operations capability from "operates
today's staging platform" to "supports a production money operation". Ordered
by what fails first in production, not by size. Each phase states the why, the
concrete how (grounded in patterns already on master), dependencies, and an
exit test. Governed by the Operations Platform Architecture Review (§7
checklist + §8 rulings).

**The go-live gate**: OP-1 through OP-3 plus the infrastructure checklist at
the end are the minimum for real money. OP-4 is needed before the first
regulator/partner data request. Everything after is scale-driven.

---

## OP-1 · FinOps levers — the payments desk can act *(blocking for go-live)*

**Why first**: a failed B2C payout or a lost STK callback is a member's money
in limbo. Today ops can see it and cannot touch it; every incident becomes a
developer page. This is the only gap that turns routine rail flakiness into
an outage.

> **Status — increment 1 (payout rail) shipped.** `PaymentOpsService`
> (`apps/payments/ops.py`) exposes `requery` and `mark_failed` for stuck payout
> `FinancialTransaction`s, healing them through the *same* callback finalize /
> reversal path (no hand-rolled journals), idempotently. The `/finops` console
> workspace shows stuck-payout, failed, and (informational) stuck-pay-in queues
> with per-movement levers gated behind `finops.retry` + step-up and dual-
> audited. `reverse` (settled-payout reversal) ships two-person via OP-3
> maker-checker. `retry_payout` re-dispatches a payout that stalled before ever
> reaching the rail (no `conversation_id`) through the canonical
> `execute_b2c_payout` door — surfaced as **Re-send** on never-dispatched rows
> (vs **Requery** once dispatched); the door's guards prevent a double-send. A
> failed payout's funds are already restored, so re-issuing is a fresh
> disbursement, not a re-send. Pay-in requery already runs automatically via
> `poll_mpesa_stk_status`. **OP-1 complete.**

**How**:
1. **Domain door first** (the review's rule — no ops button bypasses the
   pipeline): a `PaymentOpsService` in `apps/payments` exposing exactly four
   actions, each built on machinery that already exists:
   - `requery(ft)` — ask the rail for truth (Daraja STK query / B2C status
     via the provider port) and apply the result through the same callback
     path, so a lost webhook is healed identically to a received one.
   - `retry_payout(ft)` — re-submit a stuck PROCESSING/FAILED payout with the
     **same idempotency key** (the ledger guarantees no double-post; the
     provider port already normalises results).
   - `mark_failed(ft, reason)` — terminal-fail a stuck PENDING that the rail
     confirms never happened (frees the member to retry; requires a fresh
     requery result, not operator opinion).
   - `reverse(ft, reason)` — post the balanced reversal journal
     (`post_journal(reverses=...)` exists) + `transition_to(REVERSED)`.
     **Gated behind OP-3 maker-checker from day one** — reversals are the one
     lever that must never be single-handed.
2. **Ops workspace** `views_finops.py` + `/finops`: three queues that define
   the desk's day — *stuck pay-ins* (PENDING > 30 min), *stuck payouts*
   (PROCESSING > 30 min), *failed* (with reason) — each row opening the
   existing Transaction 360 with the lever panel added for
   `finops.retry` holders. Every action: `record_action` + a domain audit row
   + reason.
3. Wire the two recovery Celery tasks (`recover_stale_processing_transactions`,
   `reconcile_payments`) to also be triggerable per-transaction from the
   console (they already exist as scheduled sweeps).

**Depends on**: nothing new. **Exit test**: kill a sandbox callback
mid-flight; an operator (not a developer) heals it from the console in under
two minutes, and the journal stays balanced.

## OP-2 · System Health workspace + alerting *(blocking for go-live)*

**Why second**: the durable-event and async machinery is the platform's
nervous system; today its failure modes are numbers on a dashboard nobody is
forced to look at.

> **Status — shipped.** `/health` workspace: outbox summary + dead-letter
> browser with **requeue** (via the `apps.core.events.requeue_outbox_event`
> service door, `health.act`, audited), **worker heartbeats** (DB-backed
> `WorkerHeartbeat` stamped by a Celery `task_postrun` signal — DB rather than
> cache because web/worker are separate processes and no shared Django cache is
> configured), and **queue depths** (Redis `llen`, best-effort). Alerting:
> `ops_alerts` beat task (every 5 min) evaluates trial-balance ≠ 0, dead
> letters, outbox backlog, stuck payouts, and stale heartbeats → Sentry +
> `StaffNotice`, de-duplicated by condition key and auto-resolved when it
> clears; surfaced as a **bell** in the console shell (any operator; critical
> pulses red).

**How**:
1. **Outbox browser** (`/health`): PENDING and DEAD queues with payload
   inspection; *requeue* (DEAD → PENDING, attempts reset) via a
   `core.events` service function, `health.act`, audited. Dead-letter detail
   shows `last_error`.
2. **Worker heartbeats**: key beat tasks already run on schedules — have each
   stamp `cache.set('beat:<task>', now)` on completion (one line each);
   the health endpoint reads the stamps and flags anything stale. Queue
   depths via Redis `llen` on the four queues.
3. **Alerting — the piece that makes tiles matter**: one beat task
   (`ops_alerts`, every 5 min) evaluating exactly the dashboard's alert
   conditions — trial balance ≠ 0, dead letters > 0, oldest pending outbox
   > 10 min, stuck payouts > 0, stale heartbeat — and on breach: Sentry event
   + an ops notification row (a small `StaffNotice` table surfaced as a bell
   in the console shell). No new infra; escalation to real paging can ride
   Sentry's integrations.

**Depends on**: nothing new. **Exit test**: poison one outbox event; the bell
rings, the operator finds it in the DEAD queue, requeues it, delivery
completes.

## OP-3 · Step-up auth + maker-checker (Approvals) *(blocking before the ops team grows)*

**Why third**: until this exists, every destructive lever is single-handed.
Acceptable for two founders; indefensible for an ops team.

> **Status — step-up (TOTP) shipped.** Part 1 below is implemented:
> `StaffAccount` carries an **encrypted-at-rest** TOTP secret (Fernet via
> `apps/core/encryption.EncryptedTextField`) + hashed single-use recovery codes;
> `/api/ops/auth/totp/setup|confirm/` and `/api/ops/auth/step-up/` handle
> enrolment and elevation; `RequireStepUp` now enforces a fresh, per-operator
> `X-Ops-StepUp` elevation token (5-min) and gates the destructive levers that
> exist today — member deactivate/reactivate and community suspend/unsuspend.
> The console prompts for a code (walking first-time operators through
> enrolment) via `useStepUp()`.
>
> **Status — maker-checker (Part 2) shipped.** `OpsApprovalRequest` +
> `apps/backoffice/approvals.py` (registry + `require_approval` / `decide`)
> implement dual control: a flagged action records a pending request instead of
> executing; a *second* operator with `approvals.decide` + step-up approves,
> which runs the domain call attributed to both (self-approval structurally
> refused, 24h expiry, single-execution lock). The first flagged action is the
> money **reversal** (OP-1's deferred lever): `PaymentOpsService.reverse`
> registered as `finops.reverse`, requested from Transaction 360 and decided in
> the `/approvals` inbox. LimitRule changes, override issuance, and staff role
> changes register the same way.

**How** (the step-up mechanism ruling — TOTP — is adopted):
1. **Step-up = TOTP** *(done)*: authenticator-app enrolment on
   `StaffAccount` (secret + recovery codes); `RequireStepUp` (formerly stubbed in
   permissions.py) validates a fresh TOTP-minted elevation token within a
   5-minute window for flagged endpoints. TOTP over SMS because ops
   staff phones are the attack surface SMS can't defend, and it adds no
   SMS-gateway dependency to the money path.
2. **Approvals**: an `OpsApprovalRequest` row in backoffice — action name,
   serialized params, requester, expiry (24h), status, checker, reason —
   created *instead of executing* when a flagged action runs. A second
   operator holding `approvals.decide` (+step-up) approves → the original
   domain-service call executes attributed to both; or rejects. Self-approval
   structurally impossible (requester == checker refused).
3. **Flagged actions — start minimal and grow**: money reversals (OP-1),
   `LimitRule` create/change, control-override issuance above a threshold,
   staff role changes (OP-5). Deliberately *not* flagged: EDD clearances and
   verification decisions (single-officer flows with full evidence trails —
   adding a checker doubles cost without doubling safety; revisit on volume).
4. **Approvals inbox** workspace: pending items with full context links,
   approve/reject with step-up prompt.

**Depends on**: TOTP ruling (adopted); Part 2 depends on OP-1 for its first
money action. **Exit test (Part 1, met)**: a destructive lever refuses without a
fresh step-up token, and a token minted for one operator cannot elevate another.
**Exit test (Part 2)**: a reversal attempted by one finance operator sits pending
until a second approves with a fresh TOTP; the audit trail shows both identities
on one action.

## OP-4 · Exports & statements *(before the first regulator/partner ask)*

> **Status — increment 1 shipped.** Streamed-CSV exports
> (`apps/backoffice/views_exports.py`, `StreamingHttpResponse` + queryset
> iterator, 100k-row cap): transaction register (`reporting.export`, mirrors the
> registry filters), audit trail (`audit.export`, mirrors the audit filters),
> and per-member statement (`ledger.export`, `/ops/users/<id>/statement/?from=&to=`).
> **Every export writes an `ops.export.*` audit row** (egress is auditable).
> Surfaced as **Export** buttons on the Transactions and Audit registries and a
> **Statement** button on Member Financial 360 (fetched as an authed blob).
> Remaining: journal-by-account export, and async generation into the files app
> with expiring signed URLs for very large ranges.

**How**: streamed-CSV endpoints behind the already-declared `*.export`
capabilities — member statement (their sub-ledger lines for a period),
transaction register (filters mirroring the registry), journal export by
account/period, audit-log export. Large ranges generate async via Celery into
the existing files app with expiring signed URLs. **Every export writes an
audit row** — data egress is itself an auditable action. Surfaced as
"Export" buttons on the registries that already exist, plus a statements
block on Member Financial 360.

**Depends on**: nothing new. **Exit test**: "all movements for member X for
March" is a two-click, fully-audited CSV.

## OP-5 · Staff management console

**How**: `/staff` workspace over the existing `StaffAccount` machinery —
provision (email + temp password + `must_change_password`, as
`create_ops_admin` does), role assignment (the `ops:*` groups), forced
reset, deactivate (revokes staff sessions), department as metadata (per
ruling §8.1). **Staff 360**: profile + roles + their `record_action` history.
Role changes flagged into OP-3 approvals. The time-boxed **grants** table
ships here *only if* a real delegation need has appeared by then (per
ruling — not speculatively).

**Depends on**: OP-3 for dual-controlled role changes.

## OP-6 · Treasury & settlement *(design doc first — real project)*

The float is the last unmodelled money. **How, in outline**: daily Daraja
org-account statement ingestion (file/API) → match against the `1000` M-Pesa
float account's journal lines → a settlement-recon workspace showing
matched/unmatched lines → float top-up/withdrawal recipes in the posting map.
The exit state: the console can prove, daily, that the ledger's float equals
Safaricom's number, and every difference has a name. Requires an ADR before
code — ingestion format, matching keys, and break-handling workflow are
decisions, not defaults.

## OP-7 · Risk workspace

**How**: velocity dashboards over `ControlDecision` (it already records every
evaluation with window totals), an alert queue combining holds + repeat-deny
patterns + KYC-mismatch signals, feeding the existing EDD case flow.
Grows into the *investigations domain app* only when cross-entity case files
prove necessary (review §1 boundary rule).

## OP-8 · AML screening & regulatory filings *(vendor + counsel decisions)*

Sanctions/PEP screening lands as another `IdentityVerificationProvider`-style
port with results as first-class rows on verification cases (the V5 design
already anticipates it); STR/CTR-style filing support shapes itself around
counsel's guidance on POCAMLA obligations. Blocked on external decisions, not
architecture.

## OP-9 · Tenant-scoped staff (P6-04+)

The SACCO-partner model: `StaffAccount.tenant` (null = platform staff),
tenant-pinned ops sessions whose every query inherits the tenant guard, and
capability scoping per tenant. The one phase that is architecture work rather
than surface — ADR first. Everything already stamped with tenant FKs makes it
tractable; nothing before OP-9 blocks on it.

---

## Infrastructure go-live checklist (parallel to OP-1…3)

| Item | State | Action |
|---|---|---|
| M-Pesa production credentials + go-live | sandbox | Daraja production app, callback URLs, B2C initiator credentials |
| Real SMS gateway | console backend | activate provider account (AT_* vars exist) |
| Neon paid tier + PITR backups | free tier | upgrade; verify restore procedure once |
| R2 bucket versioning + staging bucket | prod bucket live | enable versioning; provision staging |
| Celery worker split from web dyno | in-process (P0-01 debt) | paid worker service in render.yaml |
| Rate limits review | defaults set | load-test the money paths |
| Runbooks | none | one page per OP-1/OP-2 lever: symptom → console action |
| On-call rotation + Sentry alert routing | Sentry only | wire OP-2 alerts to phones |

---

### Sequence summary

```
OP-1 FinOps levers      ──┐
OP-2 Health + alerting  ──┼── GO-LIVE GATE (with infra checklist)
OP-3 Step-up + approvals──┘        │
OP-4 Exports ────────── first regulator/partner ask
OP-5 Staff console ──── before ops team ≥ ~5
OP-6 Treasury ───────── design doc → build (first weeks of live volume)
OP-7 Risk workspace ─── first fraud wave (build the queue before it)
OP-8 AML screening ──── vendor + counsel
OP-9 Tenant staff ───── SACCO partnership signing
```

OP-1, OP-2 and OP-4 are weeks-scale builds on existing patterns. OP-3 needs
one ruling (TOTP) then follows the same shape. OP-6/8/9 are projects that
earn design docs first. The architecture requires none of them to be
retrofitted — that bill was paid already.

---

## Appendix · CSO/Support-operator coverage (reference)

A core-banking (Finacle) CSO menu was used as a *completeness checklist* for the
Support/CSO operator persona — not a spec. Most of it is branch/cash/paper/
deposit-product machinery a ledger-first mobile-money OS doesn't have (cash
deposit/withdrawal, cheque books, demand drafts, lockers, term deposits/TDS,
salary upload, cheque-stock inventory, PesaLink, merchant registration). The
instructive signal: inquiries outnumber actions ~3:1 — which validates our
read-first, 360-as-composed-read design.

What maps, and where it lives:

| CSO capability | WEPL equivalent | Status |
|---|---|---|
| Customer/Balance/Ledger inquiry | User 360 / Member Financial 360 | done |
| Transaction inquiry | Transactions registry + Transaction 360 | done |
| Audit file inquiry | Audit log workspace | done |
| Account freeze | Deactivate member / suspend community (step-up) | done |
| Reversal of charges | Reversal lever (maker-checker) | done (OP-1/OP-3) |
| Referral inbox | Approvals inbox / Support desk | done |
| Reports / statements / advices | Exports & member statements | OP-4 |
| Abnormal transactions inquiry | `ControlDecision` / velocity | OP-7 |
| Lien inquiry + maintenance | `HeldMovement` holds — surface + release (maker-checked) | gap → OP-7 |
| Customer charges inquiry | Fees view off COA `4000` on Member 360 | gap (small) |
| Standing instructions inquiry | Standing orders on Member 360 | gap (small) |
| Memo maintenance | Member-level note | gap (small) |
| Stop payment | Cancel a pending payout — sibling of `mark_failed` | fits OP-1 |

The four "gap (small)" / stop-payment items are tracked here to fold into their
listed phases; none reorder the go-live gate.
