# ADR-0025: Financial-account identity and pools as first-class accounts

- **Status:** Proposed
- **Date:** 2026-07-09
- **Deciders:** Architecture review (identity strategy)

## Context

The ledger (ADR-0001, ADR-0004) is mature: double-entry, immutable journals,
posting maps, a Chart of Accounts, rebuildable `AccountBalance` projections,
tenant-aware with RLS (ADR-0008). Two identity questions were intentionally left
open, and both now need a decision before the platform grows into Treasury,
Wallets, Escrow, Lending-at-scale and BaaS.

### Current state (ground truth)

- **`Account.id`** is a bigint sequence PK. It is immutable and is what
  `JournalLine.account` and `AccountBalance.account` reference. **The immutable
  ledger already anchors on this bigint, not on the business code.**
- **`Account.code`** is `unique=True` and — per its docstring and
  `coa.member_fund_account()` (`get_or_create(code=…)`) — is currently treated as
  *the identity / resolution key*. But the code encodes business meaning
  (`SL-CONTRIBUTION-18-U55` = fund 18, user 55). Business meaning and identity are
  conflated in one field.
- **A "pool" (a `Contribution` / `WelfareFund` / `SharesFund`) has no account of
  its own.** It is a grouping key `(fund_type, fund_id)` stamped on member
  sub-ledger accounts, all of which roll up into a *single shared* GL control
  account per type (e.g. `2000 Member Contributions Payable` for every
  contribution pool). A pool's balance is the aggregate
  `fund_balance(fund_type, fund_id) = Σcredit − Σdebit` over its member
  sub-ledgers — never a stored, constrainable row.

### Why this needs a decision

1. **Identity derived from business meaning** breaks the principle *"identity must
   never change; metadata may."* Ownership transfer (ADR-0011), pool merges,
   tenant migration, and product restructures all leave the derived `code` stale.
2. **Pools are not first-class ledger entities**, which blocks any product that
   holds money *at the pool level* (escrow, unallocated ROSCA pot, welfare
   reserves, wallets) and prevents a per-pool invariant or O(1) pool balance.
3. **External exposure** (APIs, partner/BaaS reconciliation, cross-service refs)
   has no safe account handle: the bigint PK must never be exposed (enumerable,
   leaks volume/order), and the `code` is meaning-laden and mutable.

## Decision

Two related decisions. Both are **additive** — no immutable journal is ever
rewritten, because history references the stable `Account.id`.

### A. Account identity = role separation (reject "one identifier")

Each account carries three identifiers, each with exactly one job:

| Identifier | Column | Role | Mutable? | Exposed? |
|---|---|---|---|---|
| Referential identity | `id` (bigint seq) — *exists* | All FK joins (`JournalLine`, `AccountBalance`); the hot path. | Never | **Never** |
| External identity | `account_uid` (**UUIDv7**) — *add* | Handle for APIs, statements, partner/BaaS reconciliation, cross-service refs, migrations. | Never | Yes |
| Business metadata | `code` — *demote* | Human/business label + resolution alias; searchable. | **Yes** | Operator-facing |

Plus, optionally, a cosmetic operator label `FA-{id:012d}` derived from the
bigint (same pattern as `WEPL-TXN-` / `WM-`) — a display convenience, never an
identity or an external key.

Rationale for the choices:

- **Keep the bigint as the internal identity and the only thing journals
  reference.** The premise that journals need a *new* immutable identity is
  already satisfied. Never add a second FK; never point `JournalLine` at anything
  but `Account.id` (fattening the hottest index / dual-identity drift).
- **`account_uid` = UUIDv7**, not a sequence and not ULID:
  - A sequence (`FA-000…`) is *enumerable and leaks* — unfit as an external id.
  - UUIDv7 is opaque (safe to expose), time-ordered (index locality), and a
    **standard `uuid` type** with universal tooling — beating ULID (non-standard
    text) whose only edge (sortability) UUIDv7 now provides.
  - The UUID index-cost objection applies to hot, high-cardinality *write* tables
    (`JournalLine`, billions of rows) — **not** `Account` (write-once-mostly, tens
    of millions). So `account_uid` is a **secondary** column on `Account`,
    resolved to the bigint for posting; it never enters the hot path.
  - Generate v7 in the app (native `uuidv7()` is Postgres 18+) to avoid DB-version
    coupling.
- **Demote `code` to mutable metadata** and move idempotent resolution to the
  **structured natural key `(owner, fund_type, fund_id)`** (with a unique
  constraint for sub-ledgers), so the code can change without breaking resolution
  or history. This — not the new column — is the actually-urgent, nearly-free fix.

### B. Pools become first-class control accounts

Promote each pool to its own `Account`:

- A **per-pool control account** (a `21xx`-style liability, e.g. `code =
  POOL-CONTRIBUTION-<fund_id>`), the parent of that pool's member sub-ledgers.
- Member sub-ledgers net into the pool account; pool accounts net into the shared
  GL; the GL nets to zero. A **per-pool invariant** now lives on a single row, and
  the pool balance is an O(1) read instead of an O(members) aggregate.
- **Pool-level money gets a home:** escrow, an unallocated ROSCA pot, welfare
  reserves, and future wallet/escrow balances can be held on the pool control
  account before allocation to members.
- The pool account gets the same identity treatment as (A): bigint `id`,
  `account_uid`, demoted `code`. A pool thus becomes something a Wallet/Escrow/
  BaaS API can reference by stable, opaque identity.

## Consequences

- **+** Identity survives business change: pool merges, ownership transfer, tenant
  migration, and product restructures no longer strand identity.
- **+** Safe external/BaaS exposure via an opaque, standard, stable
  `account_uid`; the bigint PK is never exposed.
- **+** Pools gain a control account → pool-level money, per-pool invariants, O(1)
  balances, and a clean surface for Treasury/Wallets/Escrow.
- **+** Entirely additive: immutable history is untouched (it references
  `Account.id`); new structure is introduced going forward, with optional
  opening-balance backfill.
- **−** A migration + backfill for `account_uid`, and a larger (ADR-gated)
  modelling change for pool control accounts.
- **−** Two live identifiers (`id`, `account_uid`) demand a hard convention —
  *bigint for joins, uid for exposure, never crossed* — enforced by review.

## Migration considerations

1. `account_uid uuid UNIQUE NULL` → backfill (generate v7 per row, oldest-first to
   preserve rough time order) → enforce `NOT NULL`. Cheap while accounts are few.
2. Generate `account_uid` in the app at account creation (in the `coa` resolution
   path), not a DB default — no Postgres-18 dependency.
3. Move `get_or_create` resolution to `(owner, fund_type, fund_id)` with a unique
   constraint, so `code` becomes cosmetic. The only non-trivial code change; the
   nightly reconcile job is the backstop.
4. Pool control accounts land later, additively: introduce the account, re-parent
   member sub-ledgers (a metadata change, not a journal rewrite), and post
   pool-level entries going forward.
5. **Never** change `JournalLine` / `AccountBalance` FKs — zero hot-path risk.
6. The `account_uid` backfill is **one-way**: once assigned (and especially once
   exposed) a uid can never be regenerated. Treat it as an irreversible, verified
   migration.

## Timing

- **Now (cheapest while the ledger is young):** (A) add `account_uid` + backfill,
  and demote `code` / move resolution to the structured key. Part of this is
  nearly free and removes a future retrofit landmine.
- **Before the first pool-level-money module (Escrow / Wallets / Treasury):**
  (B) introduce per-pool control accounts. Not speculative — a known prerequisite
  for that chapter; plan for it rather than discovering it under a deadline.
- **Not urgent for the current chama product**, which the existing model serves
  correctly.

## Hidden risks & future constraints

- **Dual-identity drift** — enforce *bigint for joins, uid for exposure, never
  crossed*. Exposing the bigint or joining on the uid yields the worst of both.
- **`account_uid` is an external alias, not a future global PK.** The bigint stays
  PK within the monolith and within any future service; cross-service references
  use the uid. Promising uid-as-global-PK would commit to re-keying an append-only
  ledger — avoid.
- **UUIDv7 sourcing** — pin one in-app implementation; do not rely on the DB.
- **Global uniqueness** — `account_uid` is globally unique (not per-tenant) so it
  is a true cross-tenant handle for BaaS.
- **Mutable-but-unique `code`** — only safe once resolution keys on
  `(owner, fund_type, fund_id)`; otherwise a rename can collide or break
  idempotency.

## Alternatives considered

- **Sequence-only external id (`FA-…`).** Rejected as an *external* id —
  enumerable and information-leaking; retained only as a cosmetic operator label.
- **ULID for `account_uid`.** Rejected — non-standard tooling for a benefit
  (sortability) that standard UUIDv7 now provides.
- **UUIDv4.** Rejected in favour of v7 — random keys sacrifice index locality for
  no opacity gain over v7.
- **Keep pools as grouping keys forever.** Rejected for the Financial-OS future —
  no home for pool-level money, no per-pool invariant, O(members) balances; fine
  only for the current product.
- **Make `account_uid` the primary key / `JournalLine` FK.** Rejected — degrades
  the hottest join and makes the append-only ledger's key immovable.
