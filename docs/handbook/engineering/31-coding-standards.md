# Engineering / 31 — Coding Standards

> The conventions that make the codebase read as one voice. Standards exist so that
> engineers stop re-deciding trivia and so a reviewer can focus on correctness, not
> style. When in doubt, **match the surrounding code** (E-12) — an existing pattern
> beats a personal preference.

---

## Language and framework baseline

- **Python 3.12**, **Django 6**, **DRF**. Backend commands run from `backend/`.
- **Type hints** on public function signatures, especially anything touching money,
  identity, or events. `post_journal()`'s signature is the model: keyword-only,
  typed, explicit.
- **Follow Django idiom.** Fat models/services, thin views; querysets over manual
  SQL; migrations for every model change. Do not fight the framework.

## Money code — the strictest standards apply

Money code is held to a higher bar than the rest of the codebase, because a bug here
is a lost or invented shilling.

- **Money is `Money`/`Decimal(20,4)`, never float** (**P-4**). No `float()` on a
  monetary value, ever.
- **Never construct a `JournalEntry`/`JournalLine` directly** — call `post_journal()`
  (**P-2**). CI enforces this.
- **Never hand-roll debits/credits** — name a recipe in `posting_map.py` (**P-5**).
- **Sign lives in the direction, not the amount.** A `Line`'s amount is always
  positive; debit/credit carries the sign. Do not smuggle negative amounts.
- **Every money write carries an idempotency key.** No exceptions; retries are
  assumed (E-5).
- **Read balances from the projection**, never from a stored counter (**P-3**).

## The forbidden list (grep-guarded)

CI fails the build if any of these reappear ([CI](../../../.github/workflows/ci.yml)):

- `LedgerEntry` or the legacy single-entry writer/queries (deleted in Phase 0).
- Mutable balance caches like `current_amount = F(...)`, `ContributionAccount`,
  `ContributionBalance`.
- Any second money-mutation path around `post_journal()`.

These are not style nits — they are structural regressions
([ADR-0002](../../adr/0002-remove-legacy-ledger-and-mutable-balances.md)). Do not
reintroduce them, and do not "temporarily" comment out the guard.

## Naming — code reads in the ubiquitous language

- **Use the [glossary](../01-glossary.md) terms exactly.** A journal line is
  `JournalLine`; a verification case is `VerificationCase`; the money door is
  `post_journal`. Do not invent synonyms (E-11).
- **Domain over mechanism.** Name for what it *means* (`decide`, `emit`,
  `record_action`), not how it's built.
- **Accounts:** identity is `id`/`account_uid`; `code` is display metadata — never
  key business logic on the human code (ADR-0025).
- **Events:** past-tense facts (something *happened*), payloads are primitive IDs.

## Structure within a module

- **Services hold behaviour; models hold state and invariants; views are thin.** A
  view validates input, calls a service, and shapes a response — it does not contain
  business logic.
- **Split god modules along sub-domain seams**, not into other modules (the
  `contributions` `services/` and `views/` packages,
  [ADR-0013](../../adr/0013-contributions-module-split.md)). A file approaching
  ~1,000 lines is a signal to split *within* its module.
- **Provider guts stay behind the port** (**P-18**). Daraja vocabulary never leaves
  the M-Pesa adapter.

## Errors, transactions, and honesty

- **Wrap money+event in one transaction** (`@transaction.atomic`) so they commit or
  roll back together (**P-9**).
- **Raise domain exceptions** (`TransitionError`, `UnbalancedJournalError`), let the
  central DRF handler shape them into the uniform API envelope
  ([API Architecture](../architecture/23-api-architecture.md)). Do not hand-format
  error responses per view.
- **Never swallow an error into an optimistic success** (**P-16**, E-6). A failure
  returns a failure status.
- **Degradation is explicit.** If code behaves differently under a dependency
  outage, that behaviour is deliberate, commented, and tested (commits #155–#157).

## Comments and docstrings

- **Comment the *why*, not the *what*.** The code says what; a comment earns its
  place by explaining a non-obvious reason or invariant. `posting.py`'s module
  docstring — stating the three guarantees — is the exemplar.
- **Document invariants at the door.** Any function that upholds a P-rule says so in
  its docstring, so the next reader knows what must not be broken.
- **No change-history in code.** Comments and docstrings describe what the code does
  and *why it must be so* — never *what changed, when, or by which PR/work-item*. Do
  not write `# P0-05: ...`, `# fixed in #154`, `(Phase 6)`, `(audit H-3)`,
  `used to ... but now ...`, or `removed in ...`. That history lives in **git and the
  ADRs**, which a future collaborator has; a phase/PR/audit-finding reference is
  context they *don't*. References to the governing **decision** (`ADR-0008`) are
  fine — they point at durable rationale, not at project archaeology. A CI guard
  (`no change-history narration in code comments`) enforces this.
- **Match comment density to the surrounding code** (E-12).

## Formatting and imports

- **Consistent formatting**, applied by tooling rather than argued in review. Match
  the repository's existing style.
- **Respect import boundaries** ([Module Boundaries](../architecture/22-module-boundaries.md)):
  the ledger imports nothing from products; products import the ledger; adapters
  import their port. A future `import-linter` contract will mechanize this
  ([Future Evolution](../program/63-future-evolution.md)).

## Tests are code, held to code standards

- **Test files** are discovered as `tests.py` and `tests_*.py`. Name them for what
  they cover (`tests_posting_map.py`, `tests_reconcile.py`).
- **Test the double-delivery / retry case** for anything idempotent (E-5).
- **The money core meets the ≥90% coverage floor** (**P-22**) — not as a vanity
  metric but because the core is where a gap is most dangerous.

See [Testing Strategy](33-testing-strategy.md).

## What review will reject on sight

- Float in money code.
- A journal built without `post_journal()` / `posting_map`.
- A reintroduced grep-guarded construct.
- Business logic in a view.
- An event carrying an ORM object.
- Provider vocabulary above a port.
- A new authoritative mutable balance column.
- An optimistic success for unconfirmed money.

Each maps to a numbered principle; review cites the number
([Core Principles](../product/03-principles.md)).

---

*Continue to [Folder Structure](32-folder-structure.md).*
