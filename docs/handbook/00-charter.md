# 00 — Charter

> The preamble. Why this handbook exists, what authority it carries, and the
> spirit in which it should be read and amended.

---

## We begin again — deliberately

Wepl did not fail. It succeeded at the only thing an early product can succeed
at: it taught us what it was actually meant to become. Over many months the team
built features, rewrote them, deleted whole modules, argued about money, and
slowly converged on a truth that was not visible at the start — that Wepl is not
a contributions app that happens to touch money, but a **Financial Operating
System** that happens, today, to serve communities.

The existing repository is the record of that journey. It contains genuinely good
work — a correctly designed double-entry core, careful state machines, idempotent
money paths, a real transactional outbox — sitting alongside architectural
compromises made under deadline and experiments that outlived their usefulness.
This handbook treats that repository as **accumulated experience, not as a
codebase to be preserved.** What earned its place is carried forward and named
here as intentional. What did not is left behind without ceremony.

This is not a rewrite mandate. Most of the code that implements what this
handbook describes already exists and is good; Phases 0–6 of the roadmap are
done. The act of "beginning again" is an act of *articulation*, not demolition:
writing down, from first principles, the system we now know we should have been
building all along — so that from here forward, **development is the
implementation of a decided architecture rather than the invention of one under
pressure.**

## What this handbook is

- The **constitution** of the platform. It states the enduring shape of Wepl:
  its vision, its principles, its domain, its architecture, and the rules that
  everything else must obey.
- **Opinionated and internally consistent.** Every significant recommendation has
  a reason. Every trade-off is named. Where two goods conflict, the handbook says
  which one wins and why, rather than leaving it to be re-litigated in every pull
  request.
- **Traceable.** Every architectural claim points back to an [ADR](../adr/README.md),
  a [roadmap phase](../roadmap/README.md), or the code that embodies it.

## What this handbook is not

- **Not a tutorial or a runbook.** It explains the design, not the keystrokes.
  Operational procedures live in the code, in `render.yaml`, and in the
  management commands; this handbook explains the *shape* they implement.
- **Not a changelog.** It describes the target state and the reasoning, not the
  history of how we got there commit by commit. The git history and the ADRs are
  the record of change.
- **Not immutable.** Unlike an ADR, a handbook chapter is *revised in place* when
  a superseding decision lands. The immutable record of *why it changed* lives in
  the new ADR; the handbook always reflects the current settled position.

## The authority it carries

When code and handbook disagree, that is a defect to be resolved — never a
difference to be tolerated. One of the two is wrong:

- If the code has drifted from a decision that still holds, **the code is wrong**
  and should be corrected.
- If reality has outrun the decision, **the handbook is stale** — write the ADR
  that changes the decision, then revise the chapter.

There is no third option in which the two are allowed to quietly diverge. That
divergence is exactly the disease this handbook exists to cure: a system whose
documented intent and actual behaviour have parted ways is a system no one fully
understands.

## How it is amended

1. A structural decision is proposed as an **ADR** (see the
   [ADR template](../adr/README.md)).
2. When the ADR is *Accepted*, the affected handbook chapters are revised in the
   same change, and the ADR is cited in them.
3. The [Decision Log](program/64-decision-log.md) and each chapter's footer keep
   the cross-references current.

A change to the code that contradicts the handbook without a corresponding ADR is
not a shortcut — it is a bug against the constitution, and review should treat it
as one.

## The reader we are writing for

Every chapter is written for **the engineer who joins Wepl three years from now**,
opens this handbook, and needs to become productive and *correct* without a
founder to ask. If a chapter would leave that person guessing about intent, it is
not finished. That reader is the ultimate judge of whether this handbook has done
its job.

---

*Continue to [Glossary & Ubiquitous Language](01-glossary.md), or jump to the
[Vision](product/01-vision.md).*
