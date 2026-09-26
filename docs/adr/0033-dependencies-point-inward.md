# ADR-0033: Dependencies point inward — the ledger is a leaf, enforced

- **Status:** Accepted (2026-09-22)
- **Date:** 2026-09-22
- **Deciders:** Architecture review — module boundaries
- **Relates to:** makes ADR-0001's "single book of record" a structural property rather
  than a convention; generalizes ADR-0031's registry contract from `apps/core` to
  `apps/ledger`; inverts the ADR-0007 controls chokepoint without moving it; relocates
  the ADR-0030 money-activity projection.

## Context

A measurement of the backend app graph on 2026-09-22 found **eleven of the nineteen
apps in a single strongly-connected component**: `activity`, `audit`, `communities`,
`contributions`, `controls`, `ledger`, `mpesa`, `payments`, `tenants`, `users`,
`verification`. Every app in that set can reach every other one, so none of them can
be reasoned about, tested, extracted or replaced on its own.

It still booted because **277 cross-app imports were written inside functions** rather
than at the top of the file, against 100 at module level. A deferred import is not a
style choice here: it is the workaround that keeps Django starting when the module
graph cannot be loaded in dependency order. Each one hides an edge that a reader (and
every tool) would otherwise see.

`apps/ledger` was in that component, which is the part that matters. ADR-0001 and
ADR-0004 say the ledger is the single book of record and `post_journal()` the only door
money walks through. But the ledger reached *upward* in four places:

| Where | Reached for | What it actually was |
|---|---|---|
| `ledger/permissions.py` | `communities`, `contributions` | `FinancialPermissions` — creator / admin / treasurer / participant role checks. Every one of its seven consumers was in `apps/contributions`. Domain authorization, filed under the ledger. |
| `ledger/coa.py` | `contributions` | `_tenant_for_fund()` — reading a pool's community to stamp the tenant on a sub-ledger account. |
| `ledger/money_activity.py` | `payments` | The ADR-0030 read projection, joining a movement to its `PaymentIntent`. All three consumers were in `apps/backoffice`. |
| `ledger/posting.py` | `controls` | The ADR-0007 limits/risk gate, called from inside `post_journal`. |

None of these are accounting. The first three are other layers' work that happened to
be filed here; the fourth is deliberate enforcement that was wired the wrong way round.

## Decision

**Dependencies point inward. `apps/ledger` depends on `apps/core` and nothing else.**

The ledger answers what a balance is. It does not answer who may move it, which rail
carried it, or whether a movement is allowed. Concretely:

1. **`FinancialPermissions` moves to `apps/contributions/permissions.py`.** It is
   domain role logic and lives with the domain it describes. Its lazy imports become
   ordinary top-level ones, because in `contributions` there is no cycle to dodge.
2. **The fund → tenant lookup is inverted** (`apps/ledger/fund_tenant.py`). The ledger
   declares the hook; `ContributionsConfig.ready()` registers the implementation, the
   same way it already registers its settlement targets. With nothing registered the
   ledger still posts and stamps `tenant=None`, which is what the old code did on any
   failure and is safe under RLS.
3. **The money-activity projection moves to `apps/payments/money_activity.py`.** The
   rail dimension is the payments layer's business. `payments` already depends on
   `ledger`; it is the reverse edge that had to go.
4. **The controls chokepoint is inverted, not moved** (`apps/ledger/chokepoint.py`).
   `post_journal` runs whatever checks are registered; `ControlsConfig.ready()`
   registers `enforce_controls`. ADR-0007's guarantee is unchanged — there is still
   exactly one enforcement point and it is still inside `post_journal` — but the ledger
   no longer needs to know who enforces. Checks raise to block a posting, and those
   exceptions propagate untouched.

**The boundary is enforced by tests, not by convention**
(`apps/core/tests_module_boundaries.py`). They parse the imports out of the source, so
a lazy import counts exactly like a top-level one, and they assert:

- `apps.core` imports no sibling app (ADR-0031, now checked).
- `apps.ledger` imports nothing but `apps.core`, and is in no cycle.
- **the remaining cycle does not grow** — `CYCLE_BASELINE` names the apps still
  entangled, and a new mutual dependency between any apps fails the build.

`CYCLE_BASELINE` is a ratchet, not an endorsement. A second test fails if it is *stale*,
so freeing an app forces the baseline down and the gain cannot be quietly given back.

## Consequences

**Easier.** The ledger can now be read, tested and reasoned about on its own; its test
module needs no domain fixtures to exist. ADR-0030's remaining slices get simpler,
because dropping `FinancialTransaction`'s columns no longer has to consider what the
ledger imports. The ≥90% ledger-core coverage gate now covers a module set with no
domain dependencies in it, so the number means what it appears to mean.

**Harder, deliberately.** Anything the ledger needs from above must now be *handed* to
it — a registry filled at `AppConfig.ready()`, or an event — rather than fetched. That
is one more indirection at the two seams where it applies, and it is the price of the
boundary.

**Unchanged.** No behaviour, no wire format, no schema, no migration. The controls gate
fires on exactly the same movements as before.

**Applied since.** Two more apps have left the cycle under this rule. `apps.controls`
stopped being reached into by `apps.verification` and registers its own reaction to a
decided case instead. `apps.mpesa` became a Daraja wire client with no sibling
dependency at all: its pay-in endpoint moved to `apps/contributions/views/collect.py`,
its webhooks to `apps/payments/views_mpesa.py`, and what a settled payment *means* is
handed to it through `apps/mpesa/settlement.py`. That one freed `apps.payments` with
it, because once nothing below the domain reached upward, payments had no path back to
itself. Eleven apps → seven. `MpesaIsARailClientTests` holds the new floor.

Then `apps.tenants` stopped subclassing the authenticator. `TenantJWTAuthentication`
existed only to run one line after the user resolved, and that subclass was the whole
of `tenants -> users`. `apps.users` and `apps.tenants` are peers — neither belongs
below the other — so unlike the cases above the registry went into `apps.core`
(`request_context.py`), which both already depend on and which holds nothing but an
opaque list of callables. `apps.audit` came out with it. Seven → five.

Finally `apps.verification` became a leaf. Two imports held it in: the case ledger wrote
the customer-facing `VerificationRequest` row on an EDD decision, and it reached into
`apps.users.admin` — another app's *admin module* — for the private helpers that tell a
KYC applicant the outcome. Both are now registered. The request row went to
`apps.controls`, which raises it in `_open_edd_case` and is the only thing that creates
one, so both halves of its lifetime finally sit together. The applicant's message went
to a new `apps/users/notifications.py` (out of `admin.py`, where notification logic
never belonged) and registers against a second slot, `kyc_decided`. That slot runs
**after** the deciding transaction commits, where `decide()`'s inline `_notify` call
sat, so a handler cannot roll a decision back — stated in the hook's docstring, because
it differs from every other seam in this ADR. Five → four.

**Not addressed.** Four apps remain in the cycle — `activity`, `communities`,
`contributions`, `users` — and they are not another seam. They are mutually entangled
through the domain itself (`contributions` imports `communities` in 24 places, and every
pair is bidirectional), and removing any single edge frees none of them. Separating them
is a question about who owns a group and its money, not an inversion. `contributions`
(6,103 lines, 19 of the backend's 73 models) remains the app that will hurt first, and
`emit()` is still used by no money-path app — the decoupling seam is not load-bearing
where the coupling is. This ADR took the graph from eleven entangled apps to four and
stops it getting worse. The rest is sequenced work, and ADR-0013's contributions split
is where it continues.

**Addendum (2026-09-26).** `activity` was not part of the knot after all: it was in
the cycle only because `communities` and `contributions` called `ActivityService`
directly. Those nine calls now emit outbox facts (`community.created`,
`contribution.paid`, …) through `emit_event`, and `apps/activity/consumers.py` turns
them into feed rows on the inline lane, idempotent on the event id. Nothing imports
`apps.activity`, so the baseline is three apps.

## Alternatives considered

**`import-linter` with a full layer contract.** The obvious tool, and the first
recommendation made. Rejected as the *first* step: a contract adopted before the fix
baselines today's graph, which writes the cycle down as the intended design. The ledger
had to come out first. A layered contract remains worth adding once more of the cycle is
resolved; the test module here is deliberately small enough to be replaced by one.

**Leave the four reaches as lazy imports.** They work. But a boundary that exists only
as a habit is not a boundary, and the measurement above is what happens over time:
nobody adds a cycle on purpose, they add one import inside one function.

**Move the controls call out of `post_journal`.** This would have removed the edge by
removing the chokepoint, and is precisely what ADR-0007 forbids. Inverting the wiring
keeps the single enforcement point and drops the dependency; there was no trade to make.
