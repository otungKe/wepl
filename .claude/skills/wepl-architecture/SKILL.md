---
name: wepl-architecture
description: WEPL's layer map, ADR ladder, module boundaries, and the two
  migrations currently in flight (ADR-0030 dissolving FinancialTransaction, and
  the deliberately-unadopted Celery worker split). Use when deciding where new
  code belongs, when touching apps/core, apps/payments/providers, the event
  outbox or deployment topology, or when something in the repo looks
  half-finished and you need to know whether it is meant to be.
---

# WEPL architecture

Django 6 backend in `backend/`. Run every backend command from `backend/`.
Read `CLAUDE.md` first; this skill is the layer beneath it.

## The layer order (never invert it)

```
views / consumers
  → authorization (core/policy.py, users/tiers.py,
                   contributions/permissions.py, backoffice/permissions.py)
  → application services (contributions/services/*, payments/services.py,
                          verification/service.py)
  → posting_map recipe  →  post_journal()  ← THE money chokepoint
  → JournalEntry / JournalLine (immutable)  +  AccountBalance (derived)
```

Rails, identity vendors and notification channels sit **below** the services
behind ports; `apps/core` sits **beside** everything and imports no business app.
`apps/ledger` imports only `apps/core` (ADR-0033) — domain role checks live in the
domain app, rail detail in `apps/payments`, and the ADR-0007 controls gate is
registered into `ledger/chokepoint.py` rather than imported by it. Both boundaries
are tested in `apps/core/tests_module_boundaries.py`, which also holds a ratchet on
the nine apps still in one import cycle: that set may only shrink. `apps/controls`
reaches verification, never the reverse: a decided EDD case releases its held
movement through a reaction controls registers into `verification/hooks.py`.

## The ADR ladder (read before changing money, eventing or payments)

`docs/adr/` — 31 ADRs. Read the directory, not just the index; the index has
fallen behind before.

Load-bearing ones:
- 0001/0002/0004 — ledger-first, no mutable balances, `post_journal()` is the
  single door.
- 0003 — `Money`, `Decimal(20,4)`, banker's rounding.
- 0005 — `PaymentProvider` port; no Daraja field names above the adapter.
- 0006/0029 — transactional outbox; the second, financial-grade delivery lane.
- 0007 — limits/risk evaluated inside the posting chokepoint.
- 0008 — shared schema + `tenant_id` + Postgres RLS.
- 0009/0010/0022/0023 — authz, session registry, KYC tiers, identity port.
- 0013 — the contributions god-service split.
- 0014/0028 — payment aggregate; settlement discovery vs propagation.
- 0025/0026/0027 — account & pool identity, the Organization spine, ownership.
- 0030 — dissolve `FinancialTransaction` (IN FLIGHT — see below).
- 0031 — core is a platform layer.

**`Accepted` does not mean implemented and `Proposed` does not mean absent.**
ADR-0027 is `Proposed` but largely merged; ADR-0024 is `Proposed` and absent.
Check the code.

## Registration discipline (ADR-0031)

Cross-cutting machinery registers itself from `AppConfig.ready()`, and
`apps/core` only ever knows an opaque name:
- policy resolvers — `core/policy.py::policy("<prefix>")`
- inline event consumers — `core/events.py::register_inline_consumer`
- settlement targets — `contributions/settlement.py::register_settlement_target`
- payment adapters — `payments/providers/registry.py::_build`
- identity adapters — `users/identity/registry.py`

The same pattern is how a *lower* app calls upward without importing the app above
it (ADR-0033). Four of these exist; do not "simplify" any of them back into an
import:
- the posting chokepoint — `ledger/chokepoint.py`, filled by `ControlsConfig`
- the fund → tenant lookup — `ledger/fund_tenant.py`, filled by `ContributionsConfig`
- a decided KYC case — `verification/hooks.py`, filled by `ControlsConfig`
- a settled M-Pesa payment — `mpesa/settlement.py`, filled by `ContributionsConfig`

Each runs synchronously in the caller's transaction, at the point the direct call
used to run, so a raising handler still aborts the caller.

Adding a branch at a call site instead of a registration is the wrong answer.

## Events

`emit()` (notification-shaped) and `emit_event()` (typed body) write an
`OutboxEvent` **in the caller's transaction**. Two lanes:
- enqueue lane → `process_outbox` → the `domain_event` signal → notifications.
- `inline_atomic` lane → one `OutboxDelivery` row per consumer →
  `process_inline_deliveries` runs the handler **inside the transaction that
  acks the row**. Money consumers live here.

Rules: emit inside the transaction, JSON primitives only (never an ORM object),
every consumer idempotent, `emit()`'s signature is fixed (~30 call sites).

**Dispatch runs in a savepoint, and that is load-bearing.** A consumer that
raises a *database* error aborts the surrounding transaction, so the relay's own
attempt to write `attempts` / `last_error` would raise too — the retry and
dead-letter path used to be dead for exactly the failure mode most worth
surviving. PR #200 wrapped each dispatch in a savepoint: the handler's writes roll
back, the relay still records the attempt, and the row eventually dead-letters.
`core/tests_outbox.py` covers both lanes with a real DB error. Do not remove that
savepoint, and do not test this path with a `RuntimeError` — it proves nothing.

## Two migrations in flight — do not "finish" either by accident

**ADR-0030 — dissolving `FinancialTransaction`.**

> **Framing call taken 2026-09-21, correct it if you disagree.** These skills
> describe FT as the strangler currently leaves it — half-alive on purpose. It is
> legacy you must still read and keep consistent, not a layer you may route
> around or start deleting.

Merged: the money-activity read projection (`payments/money_activity.py`), the
back-office readers, `payments/coverage.py`, the settlement-target registry.
Not merged: dropping FT's `mpesa_*` columns, its public id, and the model.
So FT is *intentionally* half-alive. New readers of the rail dimension go
through `PaymentIntent` or `money_activity`, never FT's columns.
`payments/coverage.py` (fixed in PR #199) measures readiness by asking whether an
FT's journal touched `coa.MPESA_FLOAT`. **It has never been run against real
data, and the backfill is deliberately unwritten until it has been.**

**Issue #161 — Celery worker split: built, tested, deliberately NOT adopted.**
`RUN_EMBEDDED_CELERY` defaults to `true` in `backend/start.sh`, so worker and
beat run inside the web process. The four paid Render services live in
`render.worker-tier.yaml`, **which Render does not read**. The reason is
commercial, not technical. Flipping the default without adding the services is
an outage: `render.yaml` sets no `autoDeploy`, a master push redeploys the API,
and with no worker the outbox, notifications and reconciliation stop silently.
`apps/core/tests_deploy_topology.py::EmbeddedCelerySwitchTests` fails the build
on either half-state. Cutover runbook: `docs/deploy/worker-tier.md`.

## Known-broken, at `68e8cf6` (2026-09-21)

- The Daraja `TransactionStatusQuery` is asynchronous, so
  `payments/providers/mpesa.py::request_payout_result` reports `unknown` on every
  path including success. The stale sweep's "ask Safaricom first" branch is
  therefore dead and every payout stuck past 60 minutes is force-failed and
  reversed, including one Safaricom settled. Moved but not fixed by #197. See
  `wepl-ledger`.
- **Production has never handled real money.** The deployment points at the
  M-Pesa sandbox. Nothing in this repo's money path has been exercised against
  real settlement, so "it works" means "it works under test".

Fixed since the first draft of these skills, kept here so you do not re-diagnose
them: the standing-orders task (#202), the share-holding and advance counters
(#200/#201/#203, now derived rather than stored), outbox dead-lettering on DB
errors (#200), and the shares-fund N+1 (#204).

## Where new code goes

| It is… | It belongs in… |
|---|---|
| a debit/credit recipe | `apps/ledger/posting_map.py` |
| a money use-case (auth + transaction + side effects) | `apps/contributions/services/<domain>.py` |
| a rail detail (wire format, credentials, a rail record) | `apps/payments/providers/<rail>.py` or `apps/mpesa/` |
| an endpoint a rail calls back on | `apps/payments/views_mpesa.py`, mapped in `config/urls_mpesa.py` — **never** in `apps/mpesa`, which imports no sibling app |
| something the rail must ask the domain | a handler registered into `apps/mpesa/settlement.py` from `AppConfig.ready()` |
| a cross-cutting mechanism | `apps/core/`, registered from `AppConfig.ready()` |
| a reaction to a settled payout | a `register_settlement_target` handler in the owning context |
| an operator action | `apps/backoffice/`, behind a capability + an `AuditEvent` |
| a structural decision | a **new** ADR (they are append-only) |

## Commit / tracking conventions

Work items are `P{phase}-{nn}` (e.g. `P0-05`) and are referenced in commit
messages, phase docs and GitHub issues. Phases live in `docs/roadmap/` and
mirror epics #4–#13. A phase marked 🟢 Done means the mechanism landed, not that
the capability is switched on.

## Not covered here

Money rules → `wepl-ledger`. Isolation → `wepl-tenancy`. Auth/RBAC →
`wepl-security`. How to prove any of it → `wepl-testing`.
