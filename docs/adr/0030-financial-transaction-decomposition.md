# ADR-0030: Decompose FinancialTransaction

- **Status:** Accepted (2026-09-17)
- **Date:** 2026-09-17
- **Deciders:** Money-movement architecture review
- **Relates to:** dissolves the orchestration object into the ledger posting
  (ADR-0004), the payment aggregate (ADR-0014), and per-context workflow; depends on
  the settlement contract (ADR-0028) and the generalized event log (ADR-0029);
  preserves ledger independence from business schemas (ADR-0025) and the
  no-mutable-state / derived-truth rule (ADR-0002); follows the strangler slicing of
  the `ContributionTransaction` retirement (ADR-0027).

## Context

`FinancialTransaction` (FT, `apps/ledger/models.py:32-217`) is described in its own
docstring as "the orchestration / state-machine layer." It lives in `apps/ledger`,
but almost nothing it holds is *ledger* concern — and almost nothing it holds is
unique to it. A field-by-field accounting against the current model shows FT is a
**join table wearing a five-state god-machine**, where nearly every field already
has a better home:

| FT field (`ledger/models.py`) | Real concern | Already lives in |
|---|---|---|
| `op_type` (:75) | business label | `JournalEntry.op_type` **and** `PaymentIntent.op_type` |
| `amount` (:78) | value | `JournalLine`s (derived) **and** `PaymentIntent.amount` |
| `idempotency_key` (:79) | posting identity | the `post_journal` key itself (ADR-0004) |
| `contribution`/`welfare_fund`/`shares_fund` (:82-93) | business context | the fund/context rows; derivable from journal-line accounts |
| `context_type`/`context_id` (:98-99) | business workflow | the `disbursement_request` / `welfare_claim` / `emergency_advance` / `standing_order` rows |
| `initiated_by` (:102) | party | `JournalEntry.created_by` **and** `PaymentIntent.initiated_by` |
| `recipient_phone` (:106), `counterparty_name` (:111) | rail detail | `PaymentIntent` (rail payout target / rail-disclosed name) |
| `mpesa_checkout_id`/`conversation_id`/`receipt` (:120-122) | rail | **`PaymentIntent.provider_ref` / `receipt` — already duplicated** |
| `failure_reason` (:126) | rail/business failure | `PaymentIntent.failure_code` / `failure_message` (structured) |
| `note` (:125) | metadata | `JournalEntry.narration` |
| `tenant` (:114) | cross-cutting | both `JournalEntry` and `PaymentIntent` carry it |

Exactly **two** things do not already have a home:

1. **`state`** (`PENDING → PROCESSING → SUCCESS → FAILED → REVERSED`, :44-72) — a
   single machine conflating three *independent* states:
   - *rail in-flight / terminal* — already `PaymentIntent.status`
     (`PENDING → SUCCEEDED | FAILED`, ADR-0014),
   - *ledger reversed* — already a reversing `JournalEntry` via `.reverses`
     (`ledger/models.py:391`),
   - *business workflow* — already each context's own status field.

   And decisively: **not every FT has a rail leg.** The internal movements
   (`EXTERNAL_INCOME`, `SURPLUS_DISTRIBUTION`, advance-repayment-from-balance,
   member↔member) are born `SUCCESS` with no `PaymentIntent` at all; for them "state"
   only ever means "the journal is posted." The machine is meaningful *only* for the
   rail-backed subset — which `PaymentIntent` already runs.
2. **`reference`** (`WEPL-TXN-000001`, derived from `FT.id`, :150-155) — the
   money-activity handle members and operators quote and search on. FT's one genuine
   reporting value.

The rail-lifecycle half of the decomposition therefore **already exists**:
`PaymentIntent` (ADR-0014) is a shadow aggregate that already owns `provider_ref`,
`receipt`, a status machine, lifecycle timestamps, structured failure, and a
`ProviderEvent` callback-history child — running in parallel, "not yet
authoritative." FT's `mpesa_*` columns are a straight duplication of a model built
to own exactly them.

The cost of leaving FT in place is the structural tension this review exists to
resolve: an *orchestration/payments* object sits inside the *financial core*
(`apps/ledger`), holding FKs to `contributions` (:82-93) and M-Pesa wire fields
(:120-122). That drags contributions ⇄ payments coupling into the ledger and
conflates business, rail, and financial state in one row — the opposite of the
bounded-context separation the rebuild is aiming at. `JournalEntry.financial_
transaction` (:386) is the only structural tie binding the immutable ledger to this
orchestration object.

## Decision

**Dissolve `FinancialTransaction`.** It holds nothing that is not already — or
better — held by `JournalEntry`, `PaymentIntent`, or the business-context rows,
except a conflated state machine that decomposes into three states in three places,
and a reference handle that becomes a read projection.

### 1. Three destinations, no shared movement object

- **Rail dimension → `PaymentIntent`** (already exists; promote to authoritative).
  Readers of `mpesa_*` / `recipient_phone` / `counterparty_name` / `failure_reason`
  move to the intent. FT's rail columns are dropped.
- **Business-workflow dimension → the owning context.** The `disbursement_request`
  / `welfare_claim` / `emergency_advance` / `standing_order` rows already carry
  workflow state; readers of `context_*` and the typed FKs move to them. The ledger
  core stops holding a back-reference to `contributions`.
- **Financial dimension → `JournalEntry`.** The posted entry (and its `.reverses`
  reversal, :391) *is* the financial fact. No separate "SUCCESS/REVERSED" flag is
  needed — posted means done, a reversing entry means reversed.

No unified "money-movement" aggregate replaces FT. The three halves have different
owners and different lifecycles; fusing them is what created the problem.

### 2. Reporting value → a money-activity read projection

FT's cross-cutting reporting role becomes a **read-only projection** over
`JournalEntry ⋈ PaymentIntent` (the ADR-0028 conclusion). It is a view, never a
source of truth (ADR-0002), so it can never drift from the ledger.

### 3. Resolved forks

- **Journal anchor after FT dies →** the journal's own **`idempotency_key`** (the
  `post_journal` key, ADR-0004) plus the **`.reverses`** self-link. "Who triggered
  this" is answered by the money-activity projection, **not** by an FK on the ledger
  core — keeping `apps/ledger` independent of business schemas (ADR-0025). Pointing
  `JournalEntry` at `PaymentIntent` instead is rejected: it re-couples the ledger to
  the rail and leaves internal (no-rail) journals unanchored.
- **The `WEPL-TXN-nnnnnn` handle →** preserved by minting a **stable public id on
  the money-activity projection**, carrying existing numbers forward. Re-deriving
  the handle from `JournalEntry.id` is rejected — it renumbers a reference customers
  and operators have already captured and quoted.

### 4. Strangler slicing (mirrors ADR-0027)

44 non-test files touch FT, so the change is sliced, not big-bang — and the
strangler is already half-run (PaymentIntent is the shadow):

- **Slice A — rail readers → `PaymentIntent`;** stop writing FT's rail columns.
- **Slice B — workflow readers → the business context** (context rows / journal-line
  accounts).
- **Slice C — reporting → the money-activity projection** (replaces FT-as-report and
  `reference`).
- **Slice D — drop the state machine and the model;** re-anchor `JournalEntry` on its
  `idempotency_key` + `.reverses`; drop FT.

Each slice keeps the trial balance at zero and the ledger authoritative throughout,
exactly as the `ContributionTransaction` retirement did.

## Consequences

- **+** The financial core (`apps/ledger`) stops holding payments/orchestration
  concerns and FKs into `contributions` — the central structural tension is removed.
- **+** No duplication: rail state has one owner (`PaymentIntent`), the financial
  fact has one owner (`JournalEntry`), workflow has one owner (each context).
- **+** State stops being conflated: the three genuinely independent states
  (rail / ledger / business) live where each is actually decided.
- **+** Reporting can never drift — it is a projection, not a stored aggregate
  (ADR-0002 preserved).
- **+** Builds entirely on ADR-0028/0029 and the existing `PaymentIntent`; needs no
  new financial primitive.
- **−** A large, multi-slice migration across ~44 files; the money-activity
  projection and its stable public-id are new surfaces to build and monitor.
- **−** `PaymentIntent` must be *promoted to authoritative* for the rail dimension
  (today best-effort, ADR-0014) before Slice A can complete — a hardening step with
  its own reconciliation implications.
- **−** Anything that today reads a single FT row for a cross-cutting "what
  happened" answer must instead read the projection; ad-hoc FT queries in ops/admin
  need migrating deliberately.

## Alternatives considered

- **Keep FT as the money-movement aggregate, just move it out of `apps/ledger`.**
  Rejected — it preserves the conflation of rail/ledger/business state in one row and
  the shared-fate coupling; relocating a god-object is not decomposing it.
- **Anchor `JournalEntry` on `PaymentIntent` after FT dies.** Rejected — re-couples
  the ledger to the payment rail and leaves internal (no-rail) journals with no
  anchor; the `idempotency_key` + `.reverses` already suffice.
- **Re-derive `WEPL-TXN-nnnnnn` from `JournalEntry.id`.** Rejected — renumbers a
  handle already quoted by members and operators; the projection carries the
  existing numbers forward instead.
- **Introduce a new unified "MoneyMovement" aggregate to replace FT.** Rejected —
  rebuilds the same god-object under a new name; the three halves have different
  owners and lifecycles and must not share one table.
- **Make the money-activity projection a stored, authoritative table.** Rejected —
  recreates the mutable-cache anti-pattern (ADR-0002); it must be a derivation over
  the ledger and the intent.
- **Big-bang rewrite across the 44 call sites.** Rejected — the codebase's proven
  pattern is the strangler (ADR-0014, ADR-0027); PaymentIntent already provides the
  shadow that makes slicing safe.
