# Phase 0 — Ledger-First Cutover (Legacy Wipe)

**Status:** 🟡 In progress (P0-01 shipped — commit `cc60527`)
**Owner:** _unassigned_
**Related ADRs:** [0001](../adr/0001-ledger-first-double-entry.md),
[0002](../adr/0002-remove-legacy-ledger-and-mutable-balances.md),
[0003](../adr/0003-money-representation.md),
[0004](../adr/0004-post-journal-single-entrypoint.md)

> This is the phase the user authorised as "wipe out all legacy code." Because the
> legacy ledger and mutable balance fields run **every** money path, the wipe is
> the ledger-first cutover. It is sequenced **additive-first**: stand the new core
> up, prove it against the old, then delete the old.

---

## Objective

Make the double-entry core (`apps/ledger/posting.py` + `coa.py` + `balances.py`)
the **single source of monetary truth**, route every money path through
`post_journal()`, and **delete** the legacy single-entry ledger and all mutable
balance fields.

## Why this is Phase 0

Every later phase (payment rails, outbox, limits, reporting) is cheap *only* once
there is a single posting chokepoint. Building any of them on the current
triple-source-of-truth would mean redoing them after the cutover.

## Pre-production reset decision

No serious testing or production traffic has occurred. Therefore we **do not
backfill** historical journals from legacy data; existing dev/test rows are
discarded on cutover. This is recorded and justified in
[ADR-0002](../adr/0002-remove-legacy-ledger-and-mutable-balances.md). (If this
assumption changes — i.e. real balances exist — `P0-09` switches from "reset" to
"backfill + parallel-run reconciliation" and Phase 0 grows by ~2 weeks.)

---

## Work items

### P0-01 — Stop-the-bleeding safety fixes *(parallelisable, do first)*
Independent of the cutover; these are live risks.
- Remove `STAGING_OTP_BYPASS=true` from `render.yaml`; add a settings assertion
  that it is falsy whenever `DEBUG=False`.
- Wire durable object storage (S3/Cloudflare R2 via `django-storages`) for
  `MEDIA` — KYC IDs/selfies currently live on the ephemeral dyno disk and are lost
  on every redeploy.
- Split Celery `worker` and `beat` onto their own services (off the web dyno).
- **Acceptance:** OTP bypass impossible in prod (test asserts); KYC upload survives
  a redeploy; `celery beat` schedule fires from a dedicated process.
- **Status (2026-06-19):** OTP-bypass guard ✅ (boot-time `ImproperlyConfigured` +
  `SMS_BACKEND` wired + flag removed from `render.yaml`; automated test in
  `apps/users/tests.py`). KYC durable storage ✅ (opt-in S3/R2). Celery split
  **deferred** — kept in the web dyno until a paid worker plan / deployment
  platform is chosen (decision is platform-agnostic, not Render-specific).

### P0-02 — Test harness + CI green gate *(prerequisite for all money changes)*
- Fix test discovery (default runner currently finds 0 tests — namespace-package
  issue); a single `python manage.py test` (or `pytest`) must collect every app.
- Triage the current 45 errors / 4 failures in `contributions`/`mpesa`: fix or
  quarantine each with a tracked follow-up issue. **No money-path code is touched
  until the suite is green.**
- Add a CI workflow (GitHub Actions) running migrations + full suite on Postgres;
  block merge on red.
- Establish a coverage floor for `apps/ledger` (≥90%) and money-path services.
- **Acceptance:** green suite in CI on every PR; coverage gate enforced.
- **Status (2026-06-19):** ✅ Discovery fixed (`apps/__init__.py`; 0→71 tests
  collected). ✅ Suite green — `OK (skipped=49)`; the 49 failures were all legacy
  money-path tests (rewrite under P0-05/06), quarantined with `@skip` and tracked
  in **issue #14** (which also logs 2 real product bugs they surfaced). ✅ CI added
  (`.github/workflows/ci.yml`): Postgres+Redis, missing-migration check, posting
  engine coverage gated ≥90% (currently ~95%; ratchets up as legacy is deleted).

### P0-03 — Money standardisation
- Introduce a `Money` value object (amount + currency) and standardise all monetary
  columns on `Decimal(20, 4)` with explicit `currency` (default `KES`).
  Today legacy uses `Decimal(12–14, 2)` while the core uses `Decimal(20, 4)`.
- Define a single quantisation/rounding policy (banker's rounding, documented).
- Data migration aligning column precision.
- **Acceptance:** one money type across the codebase; rounding policy unit-tested;
  no mixed-precision arithmetic remains (`grep` for `decimal_places=2` on money cols
  is empty).
- **ADR:** [0003](../adr/0003-money-representation.md).
- **Status (2026-06-19):** ✅ `Money` value object shipped (`apps/ledger/money.py`)
  — `Decimal(20,4)` storage precision, banker's rounding (`ROUND_HALF_EVEN`),
  3-char currency (default KES), currency-safe arithmetic/ordering, and
  unit-loss-free `allocate`/`split`. 24 unit tests; added to the CI coverage gate
  (95%). The core (`JournalLine`/`AccountBalance`) was already `Decimal(20,4)`;
  legacy `14,2` columns are intentionally **not** migrated — they're deleted in
  P0-07. `Money` is adopted by money paths in **P0-05**; surviving config columns
  (e.g. `target_amount`) are widened to `20,4` in P0-05/07 alongside that work.

### P0-04 — Chart of Accounts wiring & account resolution
- Ensure `seed_coa` runs as part of deploy/migrate (idempotent).
- Define deterministic account resolution for **every** `op_type`:
  contribution, disbursement, welfare contribution, welfare claim, advance
  disbursement, advance repayment, standing-order payout, shares purchase, fee
  revenue, M-Pesa float, suspense, and reversal.
- Document the posting recipe (which accounts get DR/CR) for each op in this file's
  **Posting Map** appendix below.
- **Acceptance:** a table-driven test posts one balanced journal per op_type and
  `trial_balance()` nets to zero.
- **Status (2026-06-19):** ✅ Done. `seed_coa` runs on deploy via migrations
  (`0004`, plus `0005` for the new `1200`/`4100` accounts). Account resolution +
  the DR/CR recipe for every op_type live in `apps/ledger/posting_map.py` (builder
  functions returning balanced `Line` lists). `apps/ledger/tests_posting_map.py`
  posts a balanced journal per op_type and asserts `trial_balance()` is zero (8
  tests). Advances design resolved (receivable model — see Posting Map appendix).
  `coa.py` + `posting_map.py` added to the CI coverage gate (96%).

### P0-05 — Rewire money paths to `post_journal()`
Replace `create_fin_transaction` + `write_ledger_entry` dual-writes with balanced
journals. Keep `FinancialTransaction` as the **orchestration/state-machine** layer;
it links to the journal via `JournalEntry.financial_transaction`.
Paths (file references are current call sites):
- `ContributionService.contribute` (`apps/contributions/services.py:285`)
- `DisbursementService._schedule_execution` / B2C success path
- `WelfareService.contribute_to_welfare` (`:794`) and `_disburse` (`:918`)
- `EmergencyAdvanceService.approve_advance` (`:1068`) and `repay` (`:1184`)
- `StandingOrderService.execute_standing_order` (`:1301`)
- M-Pesa STK callback credit (`apps/mpesa/views.py`)
- B2C failure → `reverse_journal()` (replaces `write_reversal_credit`)
- **Acceptance:** every path posts a balanced journal; idempotency preserved
  (re-delivery of an M-Pesa callback posts nothing new); integration tests assert
  resulting account balances.
- **Status (2026-06-19):** ✅ Done (strangler/additive). Every money path now posts
  a balanced journal via `post_journal` + `posting_map`, linked to the
  `FinancialTransaction`: contribute, ROSCA payout, disbursement, welfare
  contribute/claim, advance disburse/repay, standing order, shares purchase; B2C
  failure posts `reverse_financial_transaction()`. STK credit flows through
  `contribute()`. **Legacy writes intentionally remain** (additive) because
  `member_contribution_total` still feeds the advance-eligibility gate — reads flip
  in P0-06, legacy is deleted in P0-07. Advance interest-income split deferred to
  P0-06. Tests: contribute/welfare journal integration + FT-reversal; suite green
  (109), ledger gate 96%.

### P0-06 — Flip balance reads & decision gates to the ledger
- Replace `contribution_balance` / `welfare_fund_balance` / `shares_fund_balance`
  (legacy `LedgerEntry` aggregation) with `account_balance()` on the pool/member
  accounts.
- Re-point every **decision gate**: advance eligibility (80% of own contributions),
  disbursement funds-available check, welfare balance guard, ROSCA/standing-order
  payout checks.
- **Acceptance:** no business logic reads `current_amount` / `WelfareFund.balance` /
  `total_pool`; gates pass equivalent tests against ledger-derived figures.
- **Status (2026-06-19):** ✅ Done for decision gates. New `balances.fund_balance()`
  (sum of member sub-ledgers) backs every gate: disbursement (request+execution),
  advance approve, standing order, ROSCA payout, welfare submit/disburse, advance
  eligibility (→ member sub-ledger), close guard, amendment guard, milestone
  notifications. Advance repayment now splits principal/interest off the AR ledger
  balance (interest → `4100`). Tests: `fund_balance` aggregation, interest-split
  edge cases, ledger==legacy equivalence. Suite green (112), gate 96%.
  **Remaining (carried into P0-07):** presentation reads of the mutable fields
  (serializers / admin / `views.py` / `ShareHolding.percentage`) still read the
  columns — they're replaced with ledger-derived values when the columns are
  dropped. Rewriting the quarantined #14 tests is also remaining test-debt.

### P0-07 — Delete legacy *(the wipe)*
Done in two milestones (additive reads/writes were in place from P0-05/06).

**Milestone 1 — single-entry shadow ledger ✅ (2026-06-19, commit `6734702`):**
- Deleted model `LedgerEntry` (+ admin) and `apps/ledger/queries.py`; migration
  `0006` drops the table.
- Removed all `write_ledger_entry` / `write_reversal_credit` calls; B2C failure
  restores funds via `reverse_financial_transaction()` only.
- `writer.py` retained but stripped to `create_fin_transaction` (FinancialTransaction
  is the orchestration layer, kept).
- Removed the legacy `reconcile_balances` drift task + its beat schedule.
- CI guard fails if `LedgerEntry`/`write_ledger_entry`/`write_reversal_credit`/
  `ledger.queries` reappear.

**Milestone 2 — mutable balance-field caches ✅ (2026-06-19, commit `0c24ed3`):**
- Removed `Contribution.current_amount`, `WelfareFund.balance`, `SharesFund.total_pool`
  and deleted models `ContributionAccount` / `ContributionBalance` (migration `0020`).
- Removed every legacy F() write site across services / mpesa / recovery task.
- Presentation is now ledger-derived: `ContributionSerializer.current_amount`,
  `WelfareFundSerializer.balance`, `SharesFundSerializer.total_pool`, member
  balances, `ShareHolding.ownership_pct`, and both admins. List views pass a bulk
  balance dict via serializer context (new helpers `member_fund_balance` /
  `user_fund_balances` / `fund_member_balances` / `fund_balances`) to avoid N+1;
  the `ContributionBalance` prefetch is gone.
- CI guard extended to fail if the legacy ledger **or** the mutable caches/writes return.
- **Correction to original plan:** `contribution_type` and `cycle_amount` are *not*
  dead (ROSCA discriminator / cycle messaging) — they stay. `min_approvals`/`deadline`
  retained (serializer-exposed) pending a separate review.
- **Acceptance met:** no business/presentation code reads the mutable balance
  fields; app boots; suite green (113), ledger gate 92%.
- **ADR:** [0002](../adr/0002-remove-legacy-ledger-and-mutable-balances.md).

### P0-08 — Reconciliation & observability for the new core
- Schedule `recompute`/`reconcile_account` (projection vs replay) for all accounts.
- Add a global invariant check: `trial_balance()['balanced'] == True`; alert (Sentry)
  on any drift.
- Dashboard/log metrics: journals posted, unbalanced attempts rejected, reversal count.
- **Acceptance:** nightly job proves projection==replay and global Σdebit==Σcredit;
  a deliberately corrupted projection is detected and auto-repaired in a test.

### P0-09 — Cutover execution & cleanup
- Execute the reset (per pre-production decision), run `seed_coa`, deploy.
- Remove now-unused imports, update `apps/ledger/models.py` docstring to drop
  "LEGACY" sections, refresh `admin.py`.
- **Acceptance:** Phase 0 exit criteria (below) all met.

---

## Exit criteria (Phase 0 done)

- [ ] Double-entry core is the only monetary source of truth.
- [ ] `post_journal()` is the sole money-mutation entrypoint (enforced by review +
      a grep guard in CI for direct `LedgerEntry`/balance-field writes).
- [ ] All legacy code deleted; repo grep is clean.
- [ ] Every decision gate reads ledger-derived balances.
- [ ] Full test suite green in CI; ledger coverage ≥90%.
- [ ] Reconciliation proves projection==replay and a zero global trial balance.
- [x] Safety fixes (P0-01) shipped — OTP-bypass guard (+ automated test) and
      durable S3/R2 KYC media. Celery split deferred pending a platform/worker-plan
      decision (tracked above).

## Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Cutover introduces a money bug | Additive dual-path first; green tests gate; reversible via git |
| Hidden reader of a mutable field | CI grep guard + integration tests on every gate |
| M-Pesa callback double-credit | Idempotency keys retained on journals; replay test |
| Scope creep into later phases | Strict exit criteria; defer anything not listed here |

## Rollback

Each work item is a separate PR. P0-07 (destructive deletes) is the only
irreversible-feeling step and is gated on P0-05/06 being green in production-like
staging; rollback = `git revert` of the deletion PRs + re-add columns (data is
reset pre-production, so no data-loss exposure).

---

## Appendix — Posting Map (finalised in P0-04)

Implemented as builder functions in `apps/ledger/posting_map.py`, each returning a
balanced `Line` list proven by `apps/ledger/tests_posting_map.py`. Op-type strings
live in `posting_map.Op`.

| Operation | Debit | Credit | Notes |
|-----------|-------|--------|-------|
| Member contribution (no fee) | `1000` M-Pesa Float (ASSET) | `SL-CONTRIBUTION-<fund>-U<user>` (LIABILITY) | member liability ↑ |
| Member contribution (with fee) | `1000` Float | member SL (net) + `4000` Fee Revenue (fee) | 3-line journal |
| Disbursement payout | member SL (LIABILITY) | `1000` Float | funds leave pool |
| Welfare contribution | `1000` Float | `SL-WELFARE-<fund>-U<user>` | reuses contribution recipe |
| Welfare claim payout | welfare SL | `1000` Float | reuses disbursement recipe |
| Advance disbursement | `AR-<adv>-U<user>` (ASSET, under `1200`) | `1000` Float | member now owes principal |
| Advance repayment | `1000` Float | `AR-…` (principal) + `4100` Interest Income (interest) | |
| Standing order | `1000` Float | member SL | contribution recipe, `op_type=STANDING_ORDER` |
| Payout reversal (B2C fail) | reverse of original | reverse of original | via `reverse_journal()` |

**Advances design (resolved):** emergency advances use a **receivable model** — a
per-member ASSET sub-ledger `AR-<advance>-U<user>` rolling up into `1200 Advances
Receivable`. The member's contribution savings stay intact (collateral, not spent);
interest is recognised as `4100 Interest Income` on repayment. New GL accounts
`1200` and `4100` are seeded by migration `0005` (and `coa.py`).

> ROSCA multi-member payout allocation (one payee drawing from many members) is
> handled in P0-05 by composing per-member `disbursement_lines`; the builders are
> composable for that.
