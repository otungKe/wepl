# Engineering / 30 — Engineering Principles

> How we build, and what we refuse to do. The [Core Principles](../product/03-principles.md)
> (P-1..P-22) are the platform's law; these are the *engineering* dispositions that
> keep us obeying it without being told. Where a P-rule says "money moves through
> one door," these say "and here is how we work so that stays true."

---

## E-1 — The core is boring on purpose
The financial core uses mature, well-understood technology and patterns (**P-21**).
Cleverness is a cost paid by every future engineer who must understand the money
path at 2 a.m. We spend novelty at the product edge, never in the ledger. If a
solution in the core is *clever*, that is a smell, not a badge.

## E-2 — Additive before destructive
No working money code is deleted on faith (**P-7**). We build the new path,
dual-write, verify equivalence under a green suite, and only then remove the old.
Every change is reversible at the VCS level. This is not caution for its own sake —
it is the only safe way to operate on a system that is holding real money while we
change it.

## E-3 — One door per concern, and we defend the door
For each cross-cutting concern there is exactly one entry point (`post_journal`,
`decide`, `emit`, `record_action`, the provider ports). We do not add a second door
for convenience, and we add CI guards that fail the build if someone tries. A
concern with two doors is a concern that will be enforced inconsistently.

## E-4 — Truth is immutable; reads are projections
When we build something that holds important truth, we ask first: *what is the
append-only log, and what is the rebuildable projection?* ([Philosophy §3](../product/02-philosophy.md)).
We do not store mutable authoritative state that could silently drift. A design that
cannot answer this question is not finished.

## E-5 — Assume retries; build idempotency
The world is at-least-once — Celery retries, M-Pesa re-callbacks, users double-tap.
We build every money and delivery path to be idempotent on a key, and we test the
double-delivery case explicitly. We never assume exactly-once; pretending otherwise
is how systems double-charge people.

## E-6 — Fail honestly and loudly, degrade deliberately
Software tells the truth about its own state (**P-16**). A failure surfaces as a
failure; a dependency outage degrades in a *documented, decided* way (fail-open vs
fail-closed is a choice we record, per commits #155–#157), never as a silent lie or
an opaque 500. Honest failure keeps a recoverable incident from becoming a trust
breach.

## E-7 — The green gates are the guardrails; we do not merge around them
The money-core coverage floor (≥90%), the migration-drift check, the trial-balance
check, and the grep-guards are merge-blocking (**P-22**). A red gate is a repealed
principle; we fix the code, not the gate. Disabling a gate to ship is forbidden —
the gate *is* the principle, mechanized.

## E-8 — Small, reviewable, ID-tagged changes
Work is decomposed into work items (`P{phase}-{nn}`) and shipped as focused pull
requests that reference them ([Development Workflow](34-development-workflow.md)). A
change to the money path is small enough to be reasoned about in full. Big-bang
changes to money infrastructure are how you get an un-reviewable diff over a beating
heart.

## E-9 — Decisions are written down before they are built
Anything structural gets an ADR first (**P-20**), and the [handbook](../README.md)
is revised when it lands. We do not discover the architecture in the diff; we decide
it, record it, then implement it. Undocumented decisions are re-litigated forever.

## E-10 — Read the ledger's rules before touching money
Before changing money flow, eventing, or payments, read the relevant
[ADR](../../adr/README.md) and handbook chapter (the [CLAUDE.md](../../../CLAUDE.md)
instruction, generalized). The money path has invariants that are not obvious from
the code alone; the rules exist because someone already learned the hard way.

## E-11 — Names carry the domain
Code reads in the [ubiquitous language](../01-glossary.md): a `JournalLine` is a
journal line, `decide()` decides, `emit()` emits. We do not invent synonyms for
domain terms. One word, one meaning, in conversation and in code, so the two never
drift apart.

## E-12 — Match the surrounding code
New code reads like the code around it — same idioms, same naming, same comment
density. The goal is one voice across the codebase, not a patchwork of personal
styles. A reviewer should not be able to tell who wrote a given function from its
style alone.

## E-13 — Verify behaviour, not just types
A nontrivial change is exercised end-to-end — the affected flow is driven and
observed, not merely type-checked or unit-passed ([Testing Strategy](33-testing-strategy.md)).
For money, "the tests pass" is necessary but not sufficient; we watch the shilling
move.

## E-14 — Boundaries are sacred; talk through the surface
Modules communicate through documented surfaces — service functions, ports, events
— never by reaching into each other's internals ([Module Boundaries](../architecture/22-module-boundaries.md)).
An event carries IDs, not ORM objects. We keep the seams clean so the monolith stays
modular.

## E-15 — Optimize the thing that is slow, and prove it first
Balances are a projection *because* projection reads are fast enough — measured, not
guessed. We do not pre-optimize the core into cleverness (E-1); we measure, then fix
the real hotspot. A performance change to the money path is justified with numbers,
not intuition.

---

## The refusals (what we will not do, ever)

- **We will not create a second source of truth for money** (**P-1**).
- **We will not move money outside `post_journal()`** (**P-2**).
- **We will not store money as float** (**P-4**).
- **We will not weaken the production OTP-bypass guard** (**P-15**).
- **We will not merge past a red money-core gate** (**P-22**, E-7).
- **We will not leak provider vocabulary above a port** (**P-18**).
- **We will not mix the customer and operator planes** (**P-12**).
- **We will not show optimistic success for unconfirmed money** (**P-16**, E-6).

These refusals are absolute. Changing one requires a superseding ADR
([Charter](../00-charter.md)), not a pull-request exception. If you find yourself
wanting to do one of these "just this once," that is the moment to stop and write
the ADR — or, far more likely, to find the design that doesn't require it.

---

*Continue to [Coding Standards](31-coding-standards.md).*
