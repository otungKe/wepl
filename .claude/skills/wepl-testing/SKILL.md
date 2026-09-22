---
name: wepl-testing
description: How to test WEPL — real Postgres + Redis, TestCase vs
  TransactionTestCase and why the deferred ledger trigger needs the latter, the
  FakeProvider for money paths, the two CI coverage gates and the legacy
  grep-guard, and how to avoid writing a test that passes for the wrong reason.
  Use before adding or changing any test, when a test fails and the fix is not
  obvious, or when changing anything the CI gates cover.
---

# WEPL testing

Run everything from `backend/`.

```bash
python manage.py test                       # full suite
python manage.py test apps.ledger           # one app
python manage.py test apps.ledger.tests_posting_map.PostingMapTests.test_contribution
python manage.py makemigrations --check --dry-run   # CI fails on model drift
```

Discovery picks up **both** `tests.py` and `tests_*.py`. Tests need a live
Postgres **and** Redis — CI provisions them as services; locally
`docker-compose up db redis`.

**Current baseline** (verified on `master` @ `68e8cf6`, 2026-09-21):
`Ran 890 tests in 210s — OK (skipped=52)`. If your run is materially below that
count, discovery is not picking something up.

`--parallel` is not usable as-is: a failure serialises a traceback across
processes and the run dies with `TypeError: cannot pickle 'traceback' object`.
Run serially when you expect failures.

## `TestCase` vs `TransactionTestCase` — this matters here

`TestCase` wraps each test in a transaction that is **rolled back**, so it never
COMMITs. Anything whose behaviour happens at COMMIT is therefore invisible to it:

- the **deferred** balance trigger (`ledger/migrations/0003`,
  `DEFERRABLE INITIALLY DEFERRED`),
- `transaction.on_commit(...)` callbacks (unless you use `captureOnCommitCallbacks`),
- real cross-connection row locks and concurrency.

Use `TransactionTestCase` for those. The repo has three such modules —
`apps/ledger/tests.py::DeferredTriggerTests` (the reference example),
`apps/conversations/tests_tenant.py`, and
`apps/contributions/tests_standing_orders_task.py`.

That last one exists because of the most expensive version of this mistake in
the repo's history. `contributions/tasks.py::execute_due_standing_orders` called
`select_for_update()` with no ambient transaction, so it raised
`TransactionManagementError` on **every** beat tick and no standing order had
ever executed. It had no failing test because a `TestCase` supplies exactly the
transaction Celery does not — the test environment made the bug invisible. **If
the code under test runs in a Celery task, test it in a `TransactionTestCase`.**

The BEFORE UPDATE/DELETE immutability triggers (migration 0016) *do* fire inside
a `TestCase`; wrap each expected failure in its own `transaction.atomic()`
savepoint so the error does not poison the surrounding test transaction
(`DbImmutabilityTriggerTests` shows the pattern).

Postgres-specific tests guard with
`if connection.vendor != 'postgresql': self.skipTest(...)`.

## Money paths never touch the network

Use the `FakeProvider`: `apps/payments/providers/registry.py::use_provider(...)`,
or rely on `PAYMENT_PROVIDER=''` resolving to `fake` under `DEBUG`. Never mock
`post_journal` in a service test — it is the thing under test. Seed the chart of
accounts in `setUp` with `coa.seed_chart_of_accounts()` (idempotent).

## What CI enforces (`.github/workflows/ci.yml`)

In order:
1. **Legacy grep-guard** — fails the build if `LedgerEntry`, `write_ledger_entry`,
   `ledger.queries`, `ContributionAccount`, `ContributionBalance`,
   `current_amount = F(`, `total_pool = F(`, `balance = F('balance')`,
   `class Payment(`, `PaymentSerializer` or `ContributionPaymentsView` reappear
   outside migrations and tests. It is a **denylist of names that already went
   wrong**.
2. **Mutable-money-counter guard** — matches the *shape*
   `<name containing amount|balance|total|repaid|shares|…> = F(...)` anywhere in
   `apps/`, with a one-line allowlist for `AccountBalance`'s projection in
   `post_journal`. This is the rule rather than a list of past offenders; adding
   to the allowlist means something regressed.
3. `makemigrations --check --dry-run`.
4. `migrate`.
5. The full suite under `coverage`.
6. **Ledger-core coverage ≥90 %** over
   `apps/ledger/{posting,balances,coa,money,posting_map}.py`.
7. **Authz/session/isolation/audit coverage ≥90 %** over 22 modules including
   `core/policy.py`, the three `policies.py`, `users/sessions.py`,
   `users/token_views.py`, `tenants/celery_hooks.py`, `tenants/guards.py`,
   `audit/*`, `payments/{services,reconciliation}.py`, `files/*`, `search/*`.

There is **no linter, formatter or type checker** in CI. Style is convention.

Never get green by: removing a file from an `--include` list, lowering
`--fail-under`, relaxing the grep pattern, or adding `@skip`.

## Two traps this repo has already fallen into

**1. A test that passes for the wrong reason.**
`apps/contributions/tests_settlement.py::test_shares_purchase_is_idempotent_on_receipt`
replays one receipt twice and asserts `shares_count == 1.0000`. It passed for
years — but because `SharesService.purchase` **zeroed the holding** on the second
call and re-added one purchase, not because the purchase was idempotent. The same
assertion would have held for two *different* receipts, i.e. for two genuine
purchases, which was the actual bug. A member's holding only ever showed their
latest purchase, and the test said it was fine.

**Rule:** an idempotency test must distinguish "the same key replayed" from "two
different keys". Assert the **accumulated** value across ≥2 distinct operations,
then assert that a replay of one of them changes nothing. Where a service touches
both the ledger and a domain row, assert **both**: `post_journal`'s dedup does
not cover the domain row.

`tests_settlement.py::test_repeat_share_purchases_accumulate` is the companion
test that was missing; the same defect in `EmergencyAdvance.amount_repaid` was
found the same way and is covered by `tests_advance_repayment.py`. Both counters
have since been deleted and derived from the journal, but the testing rule is
what generalises.

**2. Skipping instead of fixing.**
14 money-path test classes carry
`@skip("P0-02 #14: legacy money-path test; rewrite onto post_journal() in
P0-05/06")` — 9 in `apps/contributions/tests.py`, 3 in
`apps/payments/tests_mpesa_legacy.py` and 2 in `apps/mpesa/tests.py`.
P0-05 and P0-06 are both marked 🟢 Done, so these are skips whose stated reason
has expired. They account for nearly all 52 skipped tests and cover exactly the
paths the cutover rewrote. **Green does
not mean covered here.** Never add a `@skip` to a money test to unblock a change.

Practical consequence: adding a test to one of those classes silently adds a
*skipped* test. If you need to cover an advance, a welfare claim or an M-Pesa
callback, put it in a new `tests_*.py` module rather than in
`contributions/tests.py`. Issue #14 tracks rewriting them.

## Writing a test for a money change

1. If it adds a `posting_map` builder: assert the lines balance, assert the exact
   accounts and directions, and make sure
   `test_every_recipe_balances_and_is_idempotent` covers it.
2. If it adds a service money path: assert the journal exists with the expected
   idempotency key, assert the **derived** balance (`fund_balance` /
   `member_fund_balance`), assert a replay is a no-op, and assert any domain row
   it touches is also correct after a replay.
3. If it changes a state machine: cover the legal edge, an **illegal** edge
   (`TransitionError`), a direct `.state = …` assignment, and the lost-race path
   (`rows == 0`). `apps/payments/tests_aggregate.py` is the model to copy —
   `FinancialTransaction.transition_to` currently has **no** such test.
4. If it changes DB-level behaviour: `TransactionTestCase`, and bypass the writer
   so you are testing the constraint and not the guard above it.
5. If it changes a relay or a consumer: make the handler fail with a **database**
   error, not a `RuntimeError`. The two are not interchangeable — a DB error
   poisons the surrounding transaction, which is why dispatch runs in a savepoint.
   `core/tests_outbox.py::test_database_error_is_counted_and_dead_letters` and
   `test_handler_database_error_is_counted_and_dead_letters` are the patterns.

## Highest-value missing tests (as of `68e8cf6`, 2026-09-21)

The first three items on this list when the audit ran — the standing-orders task,
share-purchase accumulation, and outbox DB-error dead-lettering — have since been
written. What is still open:

1. A `FinancialTransaction.transition_to` suite: the legal edge, an illegal edge,
   a direct `.state = …` assignment, and the lost race. Port
   `apps/payments/tests_aggregate.py`, which does all four for `PaymentIntent`.
2. A concurrency suite: two `post_journal` calls on one key from two connections;
   two workers racing one transition; two relays claiming one row.
   `TransactionTestCase` plus real threads — none of this is reachable from a
   `TestCase`.
3. An RLS **write** test exercising a policy's `WITH CHECK` clause. Five
   migrations declare one and nothing asserts a cross-tenant write is refused.
4. A test that every ADR file appears in `docs/adr/README.md`.
5. A test for the `_query_safaricom_status` / stale-payout interaction, which
   force-fails and reverses payouts Safaricom may have settled (see
   `wepl-ledger`, "Known-broken").

## Do not assume

- Do not assume green means covered: 52 of the 890 tests are skipped, nearly all
  of them from the 14 money-path `@skip` decorators, and adding a test to one of
  those classes silently adds a 53rd.
- Do not assume a passing idempotency test proves idempotency.
- Do not assume the deferred balance trigger fires in a `TestCase`.
- Do not assume CI lints or type-checks.
- Do not assume sqlite would do: the triggers, `select_for_update`, partial
  unique constraints and RLS are all Postgres-specific.
- Do not assume a test that passes in a `TestCase` proves anything about code
  that runs in a Celery task, a relay, or a second connection.
