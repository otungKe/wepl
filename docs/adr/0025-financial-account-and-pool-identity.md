# ADR-0025: Financial-account identity and pools as first-class accounts

- **Status:** Accepted
- **Date:** 2026-07-09 (accepted 2026-07-10)
- **Deciders:** Architecture review (identity strategy)

> **Implemented** in four additive increments (ledger `0010`–`0014` + the `coa`
> resolution rewrite + the ops account-browser surface): (1) `account_uid`
> (UUIDv7) + resolution decoupled from `code`; (2) canonical GL-anchored codes;
> (3) pools as first-class control accounts; (4) the Chart-of-Accounts search
> surface (`/api/ops/accounts/`, console `/ledger`). See "Canonical code scheme"
> and "Scale posture" below for the as-built detail.

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

- A **per-pool control account** (a liability under the fund-type's GL head,
  e.g. `code = 2000-0350000` for contribution pool 350 000), the parent of that
  pool's member sub-ledgers. (See "Canonical code scheme" for the exact shape.)
- Member sub-ledgers net into the pool account; pool accounts net into the shared
  GL; the GL nets to zero. A **per-pool invariant** now lives on a single row, and
  the pool balance is an O(1) read instead of an O(members) aggregate.
- **Pool-level money gets a home:** escrow, an unallocated ROSCA pot, welfare
  reserves, and future wallet/escrow balances can be held on the pool control
  account before allocation to members.
- The pool account gets the same identity treatment as (A): bigint `id`,
  `account_uid`, demoted `code`. A pool thus becomes something a Wallet/Escrow/
  BaaS API can reference by stable, opaque identity.

### C. Canonical code scheme (one searchable namespace)

Because `code` is now mutable metadata (identity lives on `id`/`account_uid`),
we standardised it into one consistent, GL-anchored, sortable shape so the whole
tree is a single searchable namespace instead of `1000`-style GL codes sitting
next to `SL-CONTRIBUTION-18-U55` sub-ledgers. Every code is prefixed by the GL
head it rolls into, then fixed-width, zero-padded segments:

| Account role | Code shape | Example |
|---|---|---|
| GL head (seeded) | `<gl>` | `2000` (Member Contributions Payable) |
| Pool control | `<gl>-<fund_id:07d>` | `2000-0350000` (contribution pool 350 000) |
| Member sub-ledger | `<gl>-<fund_id:07d>-<owner_id:09d>` | `2000-0350000-000000055` (member 55) |

Widths (`coa.POOL_CODE_WIDTH=7`, `MEMBER_CODE_WIDTH=9`) give ~10 M pools per GL
head and ~1 B members; they are display metadata, safe to widen later precisely
because the code is not identity. Human presentation of the two ends of the
range — *"how is pool 1 shown vs pool 350 000?"* — is `2000-0000001` vs
`2000-0350000`: same width, same GL anchor, sorts and searches uniformly. Codes
are generated by `coa.pool_code()` / `coa.sub_ledger_code()`; resolution keys on
`(owner, fund_type, fund_id)`, so a code restandardisation (migration `0012`)
rewrote no journal and broke no lookup. Advances (per-member receivables under
`1200`) are not pools and keep rolling up directly into their GL head.

### Scale posture (millions of members)

The sub-ledger-per-member-per-fund model is the correct one at scale — it is how
core-banking books individual customer accounts — but three ceilings are known
and named so they are engineered deliberately, not discovered under load:

1. **Hot GL-control-account balance row.** Every posting to any pool touches the
   shared GL head's `AccountBalance` row (and, now, the pool control row) — a
   write hotspot. Mitigation when it bites: *balance bucketing* (shard the
   control account's projection into N sub-rows summed on read) or drop the
   eager GL-level projection and derive it from pool rows. The per-pool control
   account (Part B) already narrows contention from one GL row to one row *per
   pool*.
2. **`JournalLine` growth.** The append-only line table is the billions-of-rows
   table. Mitigation: *time-partition* `JournalLine` (and `JournalEntry`) by
   `posted_at`/month, keeping the hot partition small and old partitions
   archivable — the immutable, never-updated shape makes this clean.
3. **Pool control accounts** are the prerequisite for O(1) pool balances and
   per-pool invariants; without them a pool balance is an O(members) aggregate.
   Shipped in Part B.

None of the three is on the critical path for the current chama product; each is
a planned lever, and none requires re-keying the ledger (identity stays on the
immovable bigint).

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

All three decisions shipped now, while the ledger is young and the migrations are
cheap (accounts number in the thousands):

- **(A) Identity — done.** `account_uid` added + backfilled (v7, oldest-first);
  `code` demoted; resolution moved to the structured `(owner, fund_type,
  fund_id)` key with race-safe unique constraints.
- **(C) Canonical codes — done.** Restandardised to the GL-anchored, fixed-width
  scheme above (a pure metadata rewrite).
- **(B) Pool control accounts — done.** Introduced per pool, member sub-ledgers
  re-parented under them; the surface for pool-level money (Escrow / Wallets /
  Treasury) is now in place ahead of those modules rather than discovered under a
  deadline.

The three scale levers (balance bucketing, `JournalLine` partitioning, and the
now-shipped pool control accounts) remain **not urgent for the current chama
product**, which the model serves correctly; they are planned, not speculative.

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
