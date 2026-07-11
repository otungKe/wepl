# Engineering / 33 — Testing Strategy

> What we test, how, and the gates that must stay green. In a financial system tests
> are not a quality nicety — they are the mechanism by which the platform's
> principles are *proven* on every commit. A green CI run is a proof that money is
> still conserved, migrations still match models, and the forbidden patterns are
> still forbidden.

---

## The philosophy of testing here

**Tests encode principles.** Each of the P-rules that can be checked mechanically
*is* checked, in CI, and a failing check is a repealed principle (**P-22**, E-7). We
do not chase a coverage number for its own sake; we test most heavily where a bug is
most dangerous — the money core, auth, isolation, audit — and we let the number be
the floor that keeps us honest there.

## The test environment

Tests need a **live Postgres + Redis** — because the ledger's correctness depends on
real Postgres features (transactions, the deferred balance-check trigger, unique
constraints). CI provisions Postgres 16 and Redis 7 as services; locally,
`docker-compose up db redis`. A test suite that mocked the database away could not
prove the invariants that matter, so we don't.

**Discovery:** both `tests.py` and `tests_*.py` are picked up. Run the suite from
`backend/`:

```bash
python manage.py test                 # full suite
python manage.py test apps.ledger      # one app
python manage.py test apps.ledger.tests_posting_map.PostingMapTests.test_contribution  # one test
```

## The layers of testing

### 1. Invariant tests (the crown jewels)
Tests that assert the platform's core guarantees hold:
- **Balance invariant** — a journal must balance; an unbalanced post raises
  `UnbalancedJournalError`; the DB trigger rejects an unbalanced commit.
- **Idempotency** — posting the same `idempotency_key` twice yields one entry and no
  double-post (the E-5 double-delivery case, tested explicitly).
- **Trial balance is zero** — `reconcile_ledger` proves Σdebit == Σcredit globally.
- **Projection rebuild** — `AccountBalance` reconstructed from lines equals the
  live projection.
These live in `apps/ledger/tests_*.py` and are the tests we least tolerate breaking.

### 2. Posting-map / recipe tests
Every canonical recipe in `posting_map.py` is tested to produce balanced, correct
debits and credits (`tests_posting_map.py`). Because services *only* post via these
recipes (**P-5**), testing the recipes tests the accounting for every product.

### 3. Domain / service tests
State machines (optimistic-locking transitions), governance thresholds/quorum,
tier gates, verification `decide()` transition table, controls/limits. These prove
the business rules, not just the plumbing.

### 4. Provider tests via `FakeProvider`
Money paths are tested end-to-end without a live rail using `FakeProvider`
([Payments Architecture](../architecture/27-payments-architecture.md)) — including
the duplicate-callback and ambiguous-money (suspense) cases. This is what makes the
money core testable to a ≥90% floor.

### 5. API tests
Endpoint behaviour, the uniform error envelope, honest status codes, the
customer/ops plane separation, throttling/degradation behaviour.

### 6. Behaviour verification (beyond the suite)
For a nontrivial change we *drive the affected flow and observe it* (E-13), not just
run unit tests — the `/verify` discipline. "The tests pass" is necessary but not
sufficient for a money change; we watch the shilling actually move.

## The CI gates (all merge-blocking)

From [`.github/workflows/ci.yml`](../../../.github/workflows/ci.yml), in order:

| Gate | What it proves | Principle |
|------|----------------|-----------|
| **Legacy-ledger grep-guard (P0-07)** | The deleted single-entry ledger and mutable balance caches have not crept back (excludes migrations/tests) | P-1/P-3, [ADR-0002](../../adr/0002-remove-legacy-ledger-and-mutable-balances.md) |
| **`makemigrations --check --dry-run`** | The schema matches the models — no silent drift | Data integrity |
| **Migrate** | Migrations apply cleanly on a fresh DB (incl. the balance trigger) | P-6 |
| **Full test suite with coverage** | Behaviour is correct across all apps | — |
| **Ledger-core coverage ≥90%** | The money core is well-tested where a gap is most dangerous | P-22 |
| **Authz / session / isolation / audit / observability / notifications / reminders coverage ≥90%** | The security-critical modules are equally well-tested | P-12/P-13/P-14/P-19 |

**A red gate is never merged around.** The gate *is* the principle mechanized;
disabling it silently repeals the rule it enforces (E-7). If a gate is wrong, fix
the gate deliberately with review — do not bypass it to ship.

## What "≥90% on the core" really means

The coverage floor is scoped to the modules where a bug hurts most — the ledger core
(`posting.py`, `balances.py`, `coa.py`, `money.py`, `posting_map.py`) and the
security-critical modules (authz, sessions, isolation, audit, observability,
notifications, reminders). Elsewhere, coverage is reported informationally. This is
deliberate: we spend our testing effort where the [threat model](../architecture/25-security-architecture.md)
says the stakes are highest, rather than diluting it evenly.

## Testing discipline for money changes

Before a money-touching change merges:
1. The relevant [ADR/handbook chapter](../../adr/README.md) has been read (E-10).
2. New behaviour is additive-first and dual-verified where it replaces old behaviour
   (E-2).
3. The idempotency/retry case is tested (E-5).
4. `reconcile_ledger` still proves zero.
5. The flow has been driven and observed, not just unit-tested (E-13).

## What we deliberately do *not* do

- **We do not mock away Postgres** for ledger tests — the invariants live in the
  database.
- **We do not test against a live payment rail** in CI — that is what `FakeProvider`
  is for.
- **We do not treat coverage as the goal** — it is a floor on the core, not a target
  everywhere.
- **We do not merge with a red gate** — ever.

---

*Continue to [Development Workflow](34-development-workflow.md).*
