# Engineering / 34 — Development Workflow

> From idea to merged, deployed change. The workflow exists to keep the platform's
> principles enforceable at the speed of normal development — so that doing the
> right thing is also the path of least resistance.

---

## The unit of work

Work is tracked as **work items**: `P{phase}-{nn}` (e.g. `P0-05`). IDs are stable
and referenced by commits, the [phase docs](../../roadmap/README.md), and GitHub
issues. Each roadmap phase is a GitHub **epic** with a checklist; the master
tracking issue links them. A work item is the smallest thing that is independently
mergeable and reviewable (E-8).

## The lifecycle of a change

```
 idea → (structural? → ADR) → branch → build additively → green locally
      → PR referencing P{n}-{nn} → CI gates → review → merge → deploy → tick the box
```

### 1. Decide before you build (if it's structural)
Anything that changes money flow, eventing, payments, identity, or a module boundary
is *structural* and gets an **ADR first** (**P-20**, E-9), with the affected handbook
chapter revised when the ADR is accepted. Non-structural changes skip straight to a
branch. The test: *would a future engineer be surprised by this decision?* If yes,
write it down first.

### 2. Read the rules for the area you're touching
Before changing the money path, read the relevant
[ADR](../../adr/README.md) and [handbook chapter](../README.md) (E-10). The
invariants are not always visible in the code; the rules exist because someone
already learned the hard way.

### 3. Branch
Develop on a feature branch. Never commit directly to the default branch. Keep the
branch focused on one work item.

### 4. Build additively
For money changes, follow **additive-before-destructive** (E-2, **P-7**): new path
first, dual-write, verify equivalence under a green suite, delete old path last.
Every step reversible at the VCS level.

### 5. Keep it green locally
Run the suite (`python manage.py test`) against a live Postgres + Redis
(`docker-compose up db redis`). Run `makemigrations --check --dry-run` to catch
drift. Run `reconcile_ledger` if you touched money. Fix red before you push — CI
will enforce it anyway (E-7).

### 6. Open a focused PR
- Reference the work item (`P3-04: velocity limits at posting chokepoint`).
- Keep the diff small enough to reason about in full — especially for money (E-8).
- **Do not open a PR unless it's asked for**; when you do, follow any repository PR
  template.

### 7. Pass the gates
CI runs the [merge-blocking gates](33-testing-strategy.md): grep-guard,
migration-drift, suite, coverage floors. All must be green. A red gate is fixed in
the code, never bypassed.

### 8. Review
Review cites principles by number ([Core Principles](../product/03-principles.md)):
"this violates **P-2** — route it through `post_journal()`." A reviewer checks new
endpoints against the plane separation (**P-12**), the money door (**P-2**), and the
tenant boundary (**P-19**) as a standing checklist. Security-sensitive changes get a
[`/security-review`](../architecture/25-security-architecture.md) pass.

### 9. Merge and deploy
Merge to the default branch triggers deployment via the [blueprint](../operations/51-deployment-strategy.md)
(Render + Neon). Migrations run as part of release. See
[Deployment Strategy](51-deployment-strategy.md) — wait, that's operations →
[Deployment Strategy](../operations/51-deployment-strategy.md).

### 10. Close the loop
Definition of Done for a work item: **code merged · acceptance criteria met · tests
green in CI · docs/ADR updated · checkbox ticked in both the phase doc and the
GitHub epic** (the roadmap's own DoD). A change is not done when it compiles; it is
done when the record reflects it.

## Commit conventions

- **Reference the work item** in the subject (`P0-05: rewire contribute() to
  post_journal`).
- **Describe the *why*** in the body for anything non-obvious, especially money and
  degradation-behaviour changes (the recent hardening commits #154–#157 are good
  models: they state the failure mode and the chosen response).
- Small, coherent commits over one giant squash for a big change.

## Branch and PR hygiene

- One work item per branch where practical.
- Rebase/keep current with the default branch; resolve conflicts locally.
- **Push and PR only when asked**; a merged PR is finished — follow-up work is a
  fresh change, not new commits on merged history (the repo's git-operations rule).

## Definition of Done (the whole roadmap)

Zooming out, the platform's DoD is the [Vision](../product/01-vision.md)'s bar: the
ledger is the only monetary truth; `post_journal()` is the sole money path carrying
limits/risk/audit; the global trial balance is provably zero in CI and prod; a new
rail/currency ships without touching financial logic; statements come straight from
the GL. Every work item is a step toward that state, and the workflow above is how
each step stays safe.

## Working with agents (and the CLAUDE.md contract)

This repository is worked by both humans and AI agents. `CLAUDE.md` at the root is
the operating contract for that work — it encodes the money rule, the eventing rule,
the payments/identity ports, the auth guard, and the layout. An agent (or engineer)
starting work reads `CLAUDE.md` and the relevant handbook chapter *before* touching
the money path. The handbook is the *why*; `CLAUDE.md` is the *always-loaded
summary*; the ADRs are the *case law*.

---

*Continue to [Documentation Standards](35-documentation-standards.md).*
