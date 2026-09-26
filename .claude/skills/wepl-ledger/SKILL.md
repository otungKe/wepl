---
name: wepl-ledger
description: The rules of WEPL's double-entry ledger — post_journal() as the only
  money door, posting_map recipes, derived balances, journal immutability,
  idempotency keys, reversal semantics, Money/rounding, and the critical
  distinction between financial-transaction state and accounting-journal state.
  Use whenever touching apps/ledger, apps/contributions/services, apps/controls,
  anything that moves or reports money, or anything that reads a balance.
---

# WEPL ledger

The double-entry ledger in `apps/ledger/` is the **single source of monetary
truth**. Violating what follows breaks CI, a Postgres trigger, or both.

## The one distinction that matters most

**Financial-transaction state ≠ accounting-journal state.** They are different
facts with different owners, and conflating them is the mistake this codebase is
actively unwinding (ADR-0030).

| | **Accounting journal state** | **Financial-transaction state** |
|---|---|---|
| Object | `JournalEntry` + its `JournalLine`s | `FinancialTransaction.state` (and, for the rail, `PaymentIntent.status`) |
| Question it answers | "What did the books record, and when?" | "Where is this movement in its workflow / on the rail?" |
| Values | none — **posted, or not posted** | `PENDING → PROCESSING → SUCCESS \| FAILED`, `SUCCESS → REVERSED` |
| Mutability | **immutable**, enforced by Python and by DB triggers | mutable, only through `transition_to()` |
| Correction | a **new reversing entry** with `reverses=<original>` | a state transition |
| Authority | **authoritative for money** | orchestration only; being dissolved |

> **Framing call taken 2026-09-21, correct it if you disagree.** This skill
> describes `FinancialTransaction` as ADR-0030 currently leaves it: the read
> projection (`payments/money_activity.py`), the back-office readers, the
> `intent_coverage` gate and the settlement registry have all landed, but the
> `mpesa_*` columns, the public id and the model itself are still here and still
> load-bearing. So FT is **legacy that you must still read and keep consistent**,
> not a layer you may route around. Write new code against `PaymentIntent` and the
> journal; do not delete FT or stop populating it on your own initiative.

Consequences you must hold on to:
- A journal **has no state machine and must never get one.** Posted means done.
  Reversed means a second entry exists whose `reverses` points at the first.
- An FT state is not evidence that money moved. Collections are created with
  `initial_state=SUCCESS` (8 call sites) and never walk the machine at all.
- Money moved ⟺ a balanced journal exists. Money crossed the *external* boundary
  ⟺ that journal touched a settlement account (`coa.MPESA_FLOAT`, code `1000`).
  That is how `payments/coverage.py` asks the question; ask it the same way.
- Never mirror journal state into a column, and never derive a journal from an
  FT state.

## The second distinction: source of truth vs derived state

- **Immutable `JournalLine`s are the truth.**
- **`AccountBalance` is a cache.** It is updated transactionally by
  `post_journal`'s projection step and can be rebuilt at any time from the lines
  (`balances.py::recompute_account_balance`). `reconcile_ledger` (nightly 02:00)
  asserts projection == replay and repairs drift.
- `balances.py::replay_account_balance` is authoritative; `account_balance` is
  the fast read. Money paths gate on the fast read — that is a deliberate
  performance choice whose safety net is the nightly reconcile.
- **There are no authoritative mutable balance columns.** ADR-0002 deleted them
  and a CI grep-guard keeps them out.

## The single door

`apps/ledger/posting.py::post_journal(...)` is the ONLY sanctioned way to create
`JournalEntry` / `JournalLine` rows (ADR-0004). It guarantees atomically:
Σdebit == Σcredit **per currency** with ≥ 2 lines; idempotency on
`idempotency_key`; a consistent `AccountBalance` update. For member-facing
movements (skipped for reversals and for journals with no FT) it runs whatever
checks are registered in `ledger/chokepoint.py` — in practice
`controls/engine.py::enforce_controls`, which `ControlsConfig.ready()` registers
there. The ledger does not import the controls app (ADR-0033).

Enforced independently by:
- `ledger/migrations/0003` — a DEFERRABLE INITIALLY DEFERRED constraint trigger
  that re-sums each journal at COMMIT.
- `ledger/migrations/0016` — BEFORE UPDATE/DELETE triggers on both journal
  tables, so `QuerySet.update()`, `bulk_update` and raw SQL are blocked too.
- `.github/workflows/ci.yml` — the legacy grep-guard, plus a **≥90 % coverage
  floor** on `posting.py, balances.py, coa.py, money.py, posting_map.py`.

## Recipes, not hand-rolled journals

Every money operation has a canonical debit/credit recipe in
`apps/ledger/posting_map.py` returning a balanced `list[Line]`. Services call a
builder; they never assemble `Line`s inline.

```
contribution           DR 1000 Float      / CR member SL (+ CR 4000 Fee)
disbursement           DR member SL       / CR 1000 Float
welfare contribution   DR 1000 Float      / CR member welfare SL
welfare claim          DR member welfare SL / CR 1000 Float
advance disbursement   DR member AR (1200)/ CR 1000 Float
advance repayment      DR 1000 Float      / CR member AR (+ CR 4100 Interest)
pool expense           DR each member SL  / CR 1000 Float
external income        DR 1000 Float      / CR 3200 pool retained surplus
surplus distribution   DR 3200 retained   / CR each member SL
reallocate to org      DR member SL       / CR org SL   (no cash moves)
```

A new operation = a new builder + a balance test in `tests_posting_map.py`.
`test_every_recipe_balances_and_is_idempotent` walks them all.

## Chart of accounts (`coa.py`)

GL heads: `1000` M-Pesa Float/Settlement (ASSET), `1100` Suspense, `1200`
Advances Receivable, `2000` Member Contributions Payable, `2100` Welfare
Payable, `2200` Shares Payable, `3000` Opening Balance Equity, `3200` Retained
Surplus, `4000` Fee Revenue, `4100` Interest Income.

Three account roles in one table:
- **GL account** — `owner`, `owner_org` and `fund_type` all unset.
- **Pool control account** — owner-less, `(fund_type, fund_id)` set (ADR-0025
  Part B). Parents the pool's sub-ledgers; its birth also anchors a
  `CustodyArrangement` (ADR-0027).
- **Sub-ledger** — a member (`owner`) or an organization (`owner_org`).

Member/org fund positions are **LIABILITY** (the platform owes them back);
emergency advances are **ASSET**; pool retained surplus is **EQUITY**.

**Resolution keys on structured identity** `(owner|owner_org, fund_type,
fund_id)`, made race-safe by partial unique constraints — *not* on the `code`
string, which is mutable display metadata. Identity for external exposure is
`Account.account_uid` (uuid7).

Read helpers that never create an account (safe in serializers/GET):
`member_fund_balance`, `org_fund_balance`, `fund_balance`, `fund_balances`,
`user_fund_balances`, `fund_member_balances`, `economic_interest`,
`advance_repaid`, `advance_repaid_totals`.
`coa.member_fund_account` **does** create — never call it from a read path.

Note: `fund_balance()` sums every account matching `(fund_type, fund_id)` —
since ADR-0025 that is the pool control account and org sub-ledgers as well as
member sub-ledgers. If you want members only, use `fund_member_balances`.

## Money, currency, rounding

- `apps/ledger/money.py::Money` — frozen `Decimal` + ISO currency, normalised to
  **4 dp** on construction, **`ROUND_HALF_EVEN`** (ADR-0003). Cross-currency
  arithmetic raises.
- `money.quantize()` is the declared single rounding entry point.
  `Money.allocate(weights)` / `Money.split(n)` split without losing minor units.
  `Money.quantized(places)` is display-only (2 dp UI, 0 dp M-Pesa).
- **Never `float`.** Coerce via `str`.
- `post_journal` balances **per currency**; a cross-currency journal squares each
  leg through an FX clearing account (`fx.py::conversion_lines`). Rates come from
  the effective-dated append-only `ExchangeRate` table.
- **PARTIAL:** precision is not uniform. `JournalLine.amount` is `Decimal(20,4)`;
  `FinancialTransaction.amount` and `PaymentIntent.amount` are `Decimal(14,2)`.
- **PARTIAL:** `contributions/services/contribution.py::_apportion_amount` is a
  second largest-remainder implementation, floor-and-distribute like
  `Money.allocate` but at **2 dp** on raw `Decimal` rather than 4 dp on `Money`.
  Same policy, different precision. Prefer `Money.allocate` in new code; do not
  add a third implementation.

## Idempotency

Every posting carries a key, and the journal key is the FT key prefixed `je-`.
Existing shapes (`payments/coverage.py` parses them — do not rename casually):

```
contrib-<fund>-<receipt>        contrib-stk-<receipt>
welfare-contrib-<fund>-<user>-<receipt>
shares-<fund>-<user>-<receipt>  advance-repay-<id>-<receipt>
disb-exec-<request_id>          reversal-<original key>
```

`post_journal` returns the existing entry on replay and re-checks after
`get_or_create`, so it is safe under Celery retry and concurrent workers.

**Idempotency is not free for anything outside the journal.** If a service also
writes a domain row, *that* write must be idempotent too — `post_journal`'s dedup
returns the existing entry and then the service's own next statement runs anyway.

Every mutable money counter this repo ever had got that wrong. `ShareHolding`'s
`shares_count` / `total_contributed` and `EmergencyAdvance.amount_repaid` both
double-counted on replay; two of the three counters that existed, the same defect
in both. All three are **gone** now — deleted as columns and derived from the
journal (`balances.py::fund_member_balances`, `advance_repaid`,
`advance_repaid_totals`; migrations `contributions/0029` and `0030`). The lesson
generalises: when a service is tempted to keep a running total, derive it
instead, and if you truly cannot, guard the write with an explicit replay check
(`JournalEntry.objects.filter(idempotency_key=f"je-{key}").exists()`) *before*
the counter moves, not after.

## Transaction boundaries and concurrency

- Services are `@transaction.atomic` and `select_for_update()` the fund row
  before reading the balance and posting.
- **No network call inside an open transaction, ever.** Reserve in the ledger,
  then `transaction.on_commit(...)` → `safe_enqueue(task, ..., critical=True)` →
  the Celery task calls the provider outside any atomic block.
  `contributions/services/disbursement.py::_schedule_execution` is the reference
  implementation.
- State machines use `UPDATE … WHERE state = <expected>`; a `rows == 0` result
  raises `TransitionError` and means another worker won.
- Relays claim with `select_for_update(skip_locked=True)`.

## Reversal

Corrections are **new entries**. `reverse_journal(original)` flips every
direction, keeps amounts and accounts, links `reverses`, and defaults the key to
`reversal-<original key>` — which makes it idempotent.
`reverse_financial_transaction(ft)` reverses the FT's primary (non-reversal)
journal and is a no-op once reversed. Reversals **bypass** the controls gate by
design: a limit must never block a reversal.

On a failed payout the reversal is **not** written by the discovery site. The
discovery site wins the FT transition and emits `payment.failed` in the same
transaction; `contributions/settlement_consumer.py::handle_settlement` (an
`inline_atomic` consumer) performs the reversal and the domain reset. Do not
short-circuit that.

## Controls at the chokepoint (ADR-0007)

`enforce_controls` runs inside `post_journal` for member-facing movements, via
`ledger/chokepoint.py` — `ControlsConfig.ready()` registers it, so there is still
exactly one enforcement point but the ledger does not import controls (ADR-0033).
Account restrictions first (`controls/restrictions.py::RestrictionService.blocks_money`),
then `LimitRule` evaluation. DENY short-circuits; otherwise the strictest outcome
wins. DENY → `LimitExceeded`, HOLD → `ControlHeld`, both raised **before any
journal is written**.

Gotcha: the `ControlDecision` audit row is written inside the transaction the
exception then rolls back, so on DENY/HOLD the row does not survive — the review
queue is rebuilt from the exception's `context` dict by the exception handler
(`apps/controls/review.py`). Do not "fix" this by writing the decision outside
the transaction without reading ADR-0007 first.

## Reporting

`ledger/reporting.py`: `trial_balance`, `trial_balance_by_currency`,
`balance_sheet`, `income_statement`, `statement_of_account`, `export_rows`. All
derive from lines, all accept `as_of` / `fund_type` / `fund_id` / `op_type` /
`tenant_id`. All endpoints in `ledger/views.py` are `IsAdminUser`.
`payments/money_activity.py` is the ADR-0030 read projection: a **view, never a
source of truth**. The rail dimension is read from the linked `PaymentIntent` and
nowhere else — FT's `mpesa_*` columns were dropped in `ledger.0021`, so an FT with
no intent simply has no rail. It lives in payments, not the ledger, because the
rail dimension is the payments layer's business (ADR-0033).

## Do not assume

- Do not assume `FinancialTransaction` is authoritative. It is being dissolved.
- Do not look for rail detail on `FinancialTransaction`. Its `mpesa_*` columns
  are gone (`ledger.0021`); the correlation id and receipt are the
  `PaymentIntent`'s, read through `payments/money_activity.py`. A CI guard fails
  the build if a rail-named field is added back to a ledger model.
- Do not assume FT state means the money moved.
- Do not assume `AccountBalance` is the truth — replay is.
- Do not assume the deferred balance trigger will fire in a `TestCase`; it fires
  at COMMIT, which a `TestCase` never reaches. Use `TransactionTestCase`.
- Do not assume every movement has a `PaymentIntent`. Payouts do — the dispatch
  records the intent *before* calling the rail — but collections still do not:
  the STK chokepoint mints an intent with no `financial_transaction` and the
  paybill (C2B) path never had an initiation to record. `manage.py
  intent_coverage` measures that gap.
- Do not assume `Proposed` ADR behaviour exists: ADR-0027's builders are merged,
  ADR-0024's fee/excise/withholding postings are not.

## Forbidden shortcuts

- Creating a `JournalEntry`/`JournalLine` outside `post_journal` — including in a
  data migration or a management command.
- Patching a balance with `AccountBalance.objects.update(...)` to make a number
  look right. Post a correcting journal.
- Editing or deleting a posted journal; disabling either trigger; reaching for
  `SET session_replication_role = replica`.
- Adding a mutable money counter "for performance" or "for reporting". The CI
  guard now matches the *shape* (`<money-ish name> = F(...)`) with a one-line
  allowlist for `AccountBalance` in `post_journal`. If you find yourself
  extending that allowlist, something has regressed — derive instead.
- Removing a file from the CI coverage `--include` list, lowering
  `--fail-under`, or relaxing the grep-guard pattern.
- Mocking `post_journal` in a service test.
- A network call inside `@transaction.atomic`.
- `float` anywhere near money; an ad-hoc `.quantize()` with a new rounding mode.
- An ORM object in an event payload.
- Writing the ADR-0030 backfill before `python manage.py intent_coverage` has
  been run against real data.

## Known-broken (verify before citing as working)

Current as of master `68e8cf6`, 2026-09-21. Re-check before relying on any of
it; the three items the first draft of this skill listed have since been fixed
and are described above as history, not as live bugs.

- **The payout rail cannot confirm a stale payout, and the sweep no longer
  guesses.** `payments/providers/mpesa.py::request_payout_result` fires a Daraja
  `TransactionStatusQuery`, whose real answer arrives asynchronously on the
  `ResultURL`, so `_query_payout_status` reports `"UNKNOWN"` on every path
  including success. That used to be treated as failure: every payout still
  `PROCESSING` after 60 minutes was force-failed and reversed, including ones
  Safaricom had settled — and `FAILED` is terminal, so the late success callback
  could not put it right. **Fixed:** tier-2 recovery now acts only on a rail
  answer. `SUCCESS` settles, a confirmed `FAILED` reverses, and `UNKNOWN` leaves
  the movement in `PROCESSING` and escalates —
  `backoffice/tasks.py::ops_alerts` raises `payouts_awaiting_decision`
  (CRITICAL) and an operator resolves it through `payments/ops.py`. So on the
  M-Pesa rail **no stale payout is ever auto-reversed**; funds stay reserved
  until a human decides, which is the intended trade. Do not "restore" the
  auto-reversal to clear the alert queue.
- **`apps/ledger` is now a leaf and must stay one (ADR-0033).** It imports
  `apps/core` and nothing else; `ledger/tasks.py` holds only `reconcile_ledger`.
  Anything the ledger needs from above is *handed* to it — `chokepoint.py` for
  the controls gate, `fund_tenant.py` for the fund → tenant lookup — never
  imported, and a lazy import inside a function is still an import.
  `apps/core/tests_module_boundaries.py` reads the AST and fails the build. A CI
  guard separately forbids any `ledger → mpesa` edge (#159, #197).
- **Production has never held real money.** The deployment points at the M-Pesa
  sandbox, so no invariant in this file has been exercised against real
  settlement. Treat "the ledger is correct" as "the ledger is correct under
  test".

## Key tests

`apps/ledger/tests.py` (`DoubleEntryTests`, `DeferredTriggerTests`,
`DbImmutabilityTriggerTests`, `ChartOfAccountsTests`),
`tests_posting_map.py::test_every_recipe_balances_and_is_idempotent`,
`tests_money.py`, `tests_fx.py`, `tests_reconcile.py`, `tests_reporting.py`,
`tests_attribution.py`, `tests_settlement_cutover.py`.

## Commands

```bash
cd backend
python manage.py seed_coa          # idempotent chart-of-accounts seed
python manage.py reconcile_ledger  # trial balance == 0 + projection == replay
python manage.py test apps.ledger
```
