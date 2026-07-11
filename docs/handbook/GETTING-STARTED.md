# Getting Started — Day 1 on Wepl

> The shortest path from "I just cloned the repo" to "I've shipped a correct change."
> This guide operationalizes the [handbook](README.md): it tells you what to read,
> how to run the system, the handful of rules you must not break, and how to pick up
> your first piece of work. Read it once end to end before you touch the money path.

New here? You are the reader this whole handbook is written for
([Charter](00-charter.md)). Welcome.

---

## 1. Understand what Wepl is (30 minutes of reading)

Do not skip this. Wepl is a **ledger-first Financial OS**, and its architecture only
makes sense once you hold three ideas. Read these, in order:

1. **[The handbook index](README.md)** — start with "The three sentences." If you
   internalize nothing else, internalize those.
2. **[Financial Architecture](domain/12-financial-architecture.md)** — the heart.
   The double-entry ledger is the single source of monetary truth, and
   `post_journal()` is the *only* door money walks through. Everything else serves
   this.
3. **[Core Principles](product/03-principles.md)** — the numbered laws (P-1…P-22).
   You will hear these cited by number in review.

Then skim the [Domain Model](domain/10-domain-model.md) and
[Module Boundaries](architecture/22-module-boundaries.md) so you know which app owns
what. Total: ~30–40 minutes. It will save you days.

> The always-loaded short version of the rules lives in
> [`/CLAUDE.md`](../../CLAUDE.md). The handbook is the *why*; `CLAUDE.md` is the
> *summary*; the [ADRs](../adr/README.md) are the *case law*.

---

## 2. Run it locally (15 minutes)

All backend work happens in `backend/` (Python 3.12, Django 6). The suite needs a
live **Postgres + Redis** — the ledger's invariants live in the database, so there is
no mocking your way around this.

```bash
# from the repo root — bring up the datastores (and optionally the full stack)
docker-compose up db redis            # just the dependencies for tests
# or:  docker-compose up               # full stack: web + celery + beat + db + redis

cd backend
python manage.py migrate               # apply migrations
python manage.py seed_coa              # seed the chart of accounts
python manage.py test                  # run the full suite — should be green
```

Sanity checks you should run often:

```bash
python manage.py makemigrations --check --dry-run   # fails if models drift from migrations
python manage.py reconcile_ledger                   # proves the trial balance == 0
python manage.py test apps.ledger                    # just the money core
```

Settings default to `config.settings.development`. `STAGING_OTP_BYPASS` lets you use
OTP `000000` locally (it is **refused in production** — P-15, never change that).

The frontends: `web/` (Next.js member app), `backoffice/` (ops console — separate
app), `mobile/` (Expo/RN). See [Frontend](frontend/40-frontend-architecture.md) and
[Mobile](frontend/41-mobile-architecture.md).

---

## 3. The rules you must not break

These are absolute. Breaking one is not a style nit — it is a defect against the
constitution ([Charter](00-charter.md)). Each maps to a numbered principle you can
look up.

- **Money moves only through `post_journal()`** (P-2). Never construct a
  `JournalEntry`/`JournalLine` yourself. CI will fail the build if you do.
- **Never hand-roll debits/credits** — name a recipe in `posting_map.py` (P-5).
- **Money is `Money`/`Decimal`, never float** (P-4).
- **Balances are read from the projection, never stored as a mutable counter** (P-3).
- **Every money write carries an idempotency key** — retries and duplicate callbacks
  are assumed (E-5).
- **Provider vocabulary (Daraja) stays behind the payments port** (P-18).
- **Customer and operator identities never mix** — separate tokens, separate apps
  (P-12).
- **Degrade honestly** — never show optimistic success for unconfirmed money (P-16).
- **Don't reintroduce the grep-guarded legacy** (`LedgerEntry`, `current_amount =
  F(...)`, `ContributionAccount`) — it was deleted in Phase 0 and CI guards it.

If you find yourself *wanting* to break one of these "just this once," stop — that is
the signal to either find the right design or write an [ADR](../adr/README.md) that
consciously changes the rule. There are no PR-level exceptions
([Engineering Principles §Refusals](engineering/30-engineering-principles.md)).

---

## 4. Make a change the right way

The full flow is in [Development Workflow](engineering/34-development-workflow.md);
here is the Day-1 version.

1. **Is it structural?** (touches money flow, eventing, payments, identity, or a
   module boundary?) → write an [ADR](../adr/README.md) first (P-20), and revise the
   affected handbook chapter when it's accepted.
2. **Read the rules for the area** you're touching — the relevant ADR + handbook
   chapter (E-10). The invariants aren't always visible in the code.
3. **Branch.** Never commit to the default branch. One work item per branch.
4. **Build additively** for money changes — new path, dual-write, verify, delete old
   last (P-7, E-2). Never delete working money code on faith.
5. **Stay green locally** — `python manage.py test`, `makemigrations --check`,
   `reconcile_ledger` if you touched money. Test the retry/duplicate case (E-5).
6. **Open a focused PR** referencing the work item (e.g. `CV-23: remove
   _legacy_b2c_result Daraja leak`). Keep the diff small enough to reason about in
   full — especially for money. *Open a PR only when it's asked for.*
7. **Pass the gates.** CI runs the [merge-blocking gates](engineering/33-testing-strategy.md):
   legacy grep-guard, migration-drift, the suite, and the ≥90% coverage floors on the
   money core and security-critical modules. **A red gate is fixed in the code, never
   bypassed** (E-7).
8. **Verify behaviour, not just types** — drive the affected flow and watch the
   shilling actually move (E-13, the `/verify` habit).

---

## 5. Pick your first work item

**We are in the convergence phase** — moving the existing (already ledger-first) code
onto the blueprint and cleaning it up. The plan is
[Convergence Plan](program/61-convergence-plan.md). Good first items, in rough order
of "safe and high-value":

### Safest first steps (docs / low runtime risk)
- **CV-01** — promote the shipped-but-*Proposed* ADRs (0005/0006/0007/0024/0025) to
  *Accepted*. Pure documentation; teaches you the ADR corpus. Great first PR.
- **CV-03** — reconcile the handbook status table and cross-refs against reality.

### High-value cleanups (real correctness debt)
- **CV-20/21/22** — discharge [issue #14](https://github.com/otungKe/wepl/issues/14):
  rewrite the quarantined legacy money-path tests against `post_journal()`, and fix
  the two real product bugs (the percentage-threshold governance crash; the
  solo-contribution creation block). This is the most valuable cleanup — it removes
  *correctness* debt.
- **CV-23** — de-couple the ledger from the M-Pesa adapter: `apps/ledger/tasks.py`
  imports `apps.mpesa` and `FinancialTransaction` carries Daraja field names
  (`mpesa_*`) — the ledger breaking its own cardinal rule (**Rule 1 / P-18**). Needs
  its own ADR; the highest-signal structural cleanup.

### Infrastructure / mechanization
- **CV-10** — split Celery from the web dyno (separate worker/beat services).
- **CV-11** — add the `import-linter` boundary contract so the module rules are
  machine-checked, not just reviewed.

Claim an item by referencing its `CV-{nn}` ID on the branch and PR, and tick it in
the [Convergence Plan](program/61-convergence-plan.md) and the relevant GitHub epic
when done. If in doubt which app a change belongs in, re-read
[Folder Structure §decision guide](engineering/32-folder-structure.md) — the answer
is almost always "the app that *owns* the model."

---

## 6. Where to look when you're stuck

| Question | Go to |
|----------|-------|
| "How does money actually move?" | [Financial Architecture](domain/12-financial-architecture.md), [User Journeys J3–J5](product/05-user-journeys.md) |
| "Which app owns this?" | [Module Boundaries](architecture/22-module-boundaries.md), [Folder Structure](engineering/32-folder-structure.md) |
| "Why is it built this way?" | the [ADR](../adr/README.md) cited in the relevant chapter |
| "What am I allowed to do?" | [Core Principles](product/03-principles.md), [Engineering Principles](engineering/30-engineering-principles.md) |
| "How do I test / deploy?" | [Testing](engineering/33-testing-strategy.md), [Deployment](operations/51-deployment-strategy.md) |
| "What should I work on?" | [Convergence Plan](program/61-convergence-plan.md), the [roadmap](../roadmap/README.md), GitHub epics #4–#13 |
| "Is money OK right now?" | `python manage.py reconcile_ledger` (trial balance == 0) |

---

## The Day-1 mental model, compressed

> The ledger is the truth and `post_journal()` is its only door. You read *why* in
> the handbook, you obey the numbered principles, you build additively, you keep the
> gates green, and you watch the money actually move before you call it done. Do that
> and you cannot go far wrong.

Welcome to Wepl. Now go read [Financial Architecture](domain/12-financial-architecture.md)
if you haven't yet — everything starts there.
