# Engineering / 35 — Documentation Standards

> How this handbook — and the wider documentation corpus — stays alive, accurate,
> and worth trusting. Documentation that has quietly drifted from reality is worse
> than none, because it is trusted while lying. These standards exist to keep the
> docs honest.

---

## The three kinds of documentation, and their rules

Wepl deliberately keeps three distinct documentation forms, each with its own
mutability rule. Confusing them is the most common documentation failure.

| Form | Location | Nature | Mutability |
|------|----------|--------|------------|
| **Handbook** | `docs/handbook/` | The enduring shape of the system — the constitution | **Revised in place** when a superseding decision lands |
| **ADR** | `docs/adr/` | One decision: context, decision, consequences — case law | **Immutable**; superseded by a new ADR, never edited |
| **Roadmap / phase docs** | `docs/roadmap/` | The sequence of work — the legislative calendar | Updated as work progresses (checkboxes, status) |

Plus **in-code documentation** (docstrings/comments) and **`CLAUDE.md`** (the
always-loaded working summary). The audit and review docs (`docs/audit/`,
`docs/review/`) are *captured snapshots* — dated, immutable records of a point-in-time
assessment.

## Handbook standards

### It describes intent, and names the gap
The handbook states the *target* shape. Where code has caught up, it says so; where
it hasn't, it states the target and points at the gap
([Charter](../00-charter.md)). It never pretends the code is somewhere it isn't.

### Code and handbook may not silently diverge
When they disagree, that is a defect (Charter): either the code is wrong and gets
fixed, or reality outran the decision and an ADR + handbook revision is owed. There
is no third state where the two quietly differ. Reviewers treat a code change that
contradicts the handbook without an ADR as a bug against the constitution.

### Every chapter earns its keep for the three-years-from-now engineer
The reader we write for is the engineer who joins in three years and needs to be
productive and *correct* without a founder to ask ([Charter](../00-charter.md)). If
a chapter would leave that person guessing about intent, it is not finished.

### Cross-reference relentlessly
Each chapter links the ADRs that justify it, the principles it enforces (by number),
and the sibling chapters it touches. The handbook is a graph, not a stack of PDFs;
the links are how a reader follows a thread from *why* to *where*.

### Cite the principle, not just the rule
When a chapter states a rule, it names the numbered principle (**P-n**) and the ADR
behind it, so a reader can trace any claim to its decision. Assertions without
traceability rot; traceable ones can be checked.

### Explain the why, always
The handbook's distinguishing value over the code is that it explains *why*. A
chapter that only restates *what* the code does is redundant with the code; the
enduring value is the reasoning and the trade-offs named.

### One voice, the ubiquitous language
Documentation uses the [glossary](../01-glossary.md) terms exactly, like the code
(E-11). A term means one thing in the code, the API, the UI, and the docs.

## ADR standards

- **Follow the template** ([ADR README](../../adr/README.md)): Status · Date ·
  Deciders · Context · Decision · Consequences · Alternatives considered.
- **Immutable.** To change a decision, write a new ADR that supersedes the old one
  and note the supersession in both. Never edit an accepted ADR's decision.
- **State the alternatives you rejected and why** — a decision without its rejected
  alternatives is a decision no one can safely revisit.
- **Structural changes require one before they're built** (**P-20**, E-9).

## In-code documentation standards

- **Comment the *why*, not the *what*** (E-11/E-12). `posting.py`'s module docstring
  — enumerating its three atomic guarantees — is the house exemplar.
- **Document invariants at the door.** A function that upholds a P-rule says so, so
  the next reader knows what must not break.
- **Match the surrounding density** — do not over- or under-comment relative to the
  file.

## `CLAUDE.md` standards

`CLAUDE.md` is the always-loaded operating summary for humans and agents: the money
rule, the eventing rule, the ports, the auth guard, the layout, the commands. It is
kept **short and current** — it is a summary that points at the handbook and ADRs
for depth, not a duplicate of them. When a core rule changes (via ADR), `CLAUDE.md`
is updated in the same change if the rule it states has moved.

## Keeping the status table honest

The handbook [README](../README.md) carries a status table. It is updated when a
section's state genuinely changes — not aspirationally. "Drafted" means the chapter
exists and is consistent with the current code and ADR corpus; a chapter that has
fallen behind a superseding ADR is *stale* until revised, and saying so is better
than pretending.

## When you change the code, change the docs — in the same change

The single most important documentation habit: **a change that alters intent updates
the handbook (and, if structural, adds the ADR) in the same pull request.** Docs
updated "later" are docs updated never. The roadmap's Definition of Done makes this
explicit — "docs/ADR updated" is part of *done*, not a follow-up.

## Anti-patterns (rejected)

- **Docs as aspiration** — describing a system we wish we had as if we have it.
- **Editing an accepted ADR's decision** — that erases the record; supersede
  instead.
- **A handbook chapter that only restates the code** — no *why*, no value.
- **Divergence tolerated** — code and handbook disagreeing with no defect filed.
- **`CLAUDE.md` grown into a second handbook** — it is a summary, kept lean.

---

*Return to the [Engineering index](../README.md#4-engineering), or continue to
[Frontend / Frontend Architecture](../frontend/40-frontend-architecture.md).*
