# Domain / 12 — Financial Architecture

> **The heart of Wepl.** If you read one chapter, read this one. Everything else in
> the platform exists to feed, protect, or read from what is described here: a
> double-entry general ledger that is the single, provable source of monetary
> truth, entered through exactly one door.

Grounded in [ADR-0001](../../adr/0001-ledger-first-double-entry.md) through
[ADR-0007](../../adr/0007-controls-at-posting-chokepoint.md),
[ADR-0024](../../adr/0024-fee-and-tax-postings.md), and
[ADR-0025](../../adr/0025-financial-account-and-pool-identity.md); realised in
`backend/apps/ledger/`.

---

## 1. The central claim

**Money is conserved, and Wepl can prove it at any instant.** That single sentence
is the platform's reason to be trusted. It is achievable only with double-entry
accounting — a design refined over five centuries precisely because it makes
conservation *provable*: every movement debits one account and credits another by
the same amount, so the sum of all balances is always zero. A system that cannot
produce a zero trial balance cannot prove it hasn't lost money; it can only assert
it.

## 2. The one hard rule

> **`post_journal()` (`apps/ledger/posting.py`) is the ONLY door money walks
> through.** It is the sole sanctioned way to create `JournalEntry` / `JournalLine`
> rows.

This is **P-2**, and it is not a convention — it is enforced. A CI grep-guard fails
the build if money is moved any other way, and legacy single-entry constructs
(`LedgerEntry`, mutable `current_amount = F(...)` caches) are blocked from
reintroduction. The narrowness of this door is the whole design: because there is
exactly one place money moves, there is exactly one place to add limits, risk, AML,
audit, currency conversion, and settlement. Widen the door and you lose that
property forever.

## 3. What `post_journal()` guarantees, atomically

From the writer's own contract:

1. **Balance** — Σdebit == Σcredit, with ≥2 lines. Unbalanced input raises
   `UnbalancedJournalError` before anything is written.
2. **Idempotency** — keyed on a unique `idempotency_key`. A replay (Celery retry, a
   duplicated M-Pesa callback, a double-tap) returns the *existing* entry untouched
   and posts nothing new. This is what makes money paths safe under the
   at-least-once world of retries and callbacks.
3. **Consistent projection** — the `AccountBalance` projection is updated in the
   same transaction, so a balance read never sees a half-applied entry.
4. **Independent DB re-check** — a **deferred constraint trigger** (migration
   `0003`) re-verifies Σdebit == Σcredit at COMMIT, *independently of the
   application code*. Even a hypothetical bug in the writer cannot commit an
   unbalanced entry. The application guard is the convenient check; the database is
   the last line of defence.

The combination — application invariant + idempotency + a database trigger that
does not trust the application — is why the ledger is trustworthy rather than
merely careful.

## 4. The object model

```
FinancialTransaction  ──1..*──►  JournalEntry  ──2..*──►  JournalLine  ──►  Account
   (human-legible                 (one atomic,             (one debit or       (COA node;
    grouping; the                  immutable event;         one credit;         GL account
    "a payment"                    idempotency_key)         immutable atom)     or member
    a member sees)                                                              sub-ledger)

Account  ──derives──►  AccountBalance   (projection; rebuildable; a cache, never truth)
```

- **`JournalEntry`** — one atomic, immutable financial event; balanced set of
  lines; carries `idempotency_key`, `op_type`, optional `reverses` link, narration.
  Never mutated after commit.
- **`JournalLine`** — the immutable atom: one direction (debit/credit), one
  positive amount, one account. Sign lives in the direction, never in the amount.
- **`Account`** — a node in the [Chart of Accounts](#5-the-chart-of-accounts).
  Identity is `id`/`account_uid`; the human-readable `code` is *display metadata*,
  not identity (ADR-0025 — a decision that lets codes be restandardised without
  breaking references).
- **`AccountBalance`** — a derived, indexed projection of an account's balance.
  **Rebuildable by replaying journal lines.** This is the cache that **P-3** insists
  is never treated as truth; there are no authoritative mutable balance columns
  anywhere in the domain.
- **`FinancialTransaction`** — the member-facing grouping over one or more journal
  entries: what a human recognises as "a payment," carrying the searchable
  reference and counterparty name (ADR-0025). It exists so that ledger correctness
  and human legibility are *both* served without compromising either.

## 5. The Chart of Accounts

The COA (`apps/ledger/coa.py`) is the catalogue of accounts and the rules that
resolve a *logical* account to a *row*. Every resolver is idempotent — the same
logical account always maps to the same row.

**Canonical GL accounts (seeded once, via `seed_coa`):**

| Code | Type | Account |
|------|------|---------|
| `1000` | Asset | M-Pesa Float / Settlement |
| `1100` | Asset | Suspense |
| `1200` | Asset | Advances Receivable *(parent of advance sub-ledgers)* |
| `2000` | Liability | Member Contributions Payable *(parent of contribution sub-ledgers)* |
| `2100` | Liability | Welfare Payable |
| `2200` | Liability | Shares Payable |
| `3000` | Equity | Opening Balance Equity |
| `4000` | Income | Fee Revenue |
| `4100` | Income | Interest Income *(emergency-advance interest)* |

**Sub-ledger accounts (created lazily on first use):** each member's stake in a
fund is its own account, rolling up into a GL "head." A member's contribution
liability is a sub-ledger under `2000`; an advance is a sub-ledger under `1200`.
This means the pool's total is not a stored number — it is the sum of its members'
sub-ledger balances, all derived from journal lines.

**Codes are anchored, sortable, and GL-headed** (ADR-0025): one fixed-width,
sortable shape for every account so the whole tree is a single searchable
namespace. Because identity is `id`/`account_uid` and the code is metadata, codes
can be widened or restandardised later without breaking a single reference — which
is exactly what ADR-0025's increments did.

**Pools are first-class accounts** (ADR-0025): a fund's control account is a real
account, so fund-level movements live in the same addressable namespace as
everything else.

## 6. The posting map — recipes, not hand-rolled journals

**P-5: never hand-roll a journal.** Every money operation has a canonical
debit/credit recipe in `apps/ledger/posting_map.py` that returns a balanced
`list[Line]`. Services call these builders; they never assemble debits and credits
inline. The recipe is where the *accounting* is decided, reviewed, and tested;
scattering that logic into services would scatter the platform's accounting truth
into places no one audits.

Representative recipes (the spine of [User Journeys](../product/05-user-journeys.md)):

- **Contribution in:** Dr `1000` M-Pesa Float · Cr member sub-ledger under `2000`
  (· Cr `4000` Fee Revenue for any fee).
- **Payout out:** Dr the member/pool liability · Cr `1000` M-Pesa Float.
- **Advance out:** Dr member sub-ledger under `1200` Advances Receivable · Cr `1000`.
- **Advance repayment + interest:** Dr `1000` · Cr `1200` sub-ledger · Cr `4100`
  Interest Income.
- **Fee / excise / withholding:** canonical postings per
  [ADR-0024](../../adr/0024-fee-and-tax-postings.md).

## 7. Money representation

Money is the `Money` value object (`apps/ledger/money.py`): a `Decimal` amount plus
a currency, stored as `Decimal(20,4)`. **Never float** (**P-4**,
[ADR-0003](../../adr/0003-money-representation.md)) — float silently loses
fractions of a cent, which in a ledger is silently losing money. Four decimal
places give headroom for minor-unit currencies and per-unit fee math; the currency
travels *with* the amount so that multi-currency (Phase 5) is a property of every
amount rather than a retrofit.

## 8. Controls at the chokepoint

Because there is one door, limits and risk live *at* that door
([ADR-0007](../../adr/0007-controls-at-posting-chokepoint.md), `apps/controls`).
Velocity checks, per-member and per-community limits, and (eventually) AML/fraud
signals are evaluated where money moves, not sprinkled across features. Operators
can apply a `ControlOverride` where policy allows — itself audited. This is the
architectural pay-off of the single door: the next compliance requirement has
exactly one place to be implemented and cannot be forgotten in a feature that
happens to move money by another route (because there is no other route).

## 9. Reporting straight from the GL

Because the ledger *is* the system, financial statements are generated **from** it,
not reconstructed from application state (`apps/ledger/reporting.py`, Phase 4):
trial balance, account statements, and audit exports read journal lines directly. A
report can never disagree with the book of record, because it *is* the book of
record, summed.

## 10. Multi-currency and FX

Currency is threaded into `Money` from the start; per-currency balancing and FX
(`apps/ledger/fx.py`, `ExchangeRate`, Phase 5) mean a journal balances *within each
currency* and cross-currency movements post explicit FX legs. The doors were left
open for this from Phase 0 (currency on every amount) so that turning it on did not
require touching existing money logic (**P-17**).

## 11. Reconciliation & recovery

- `reconcile_ledger` verifies the global trial balance is zero (**P-6**) and is run
  in CI and in production.
- The `AccountBalance` projection is **rebuildable from journal lines**, so a
  corrupted or lagging projection is a *replay*, not an incident. This is the
  [Philosophy §3](../product/02-philosophy.md) "disposable projection" made
  operational.
- Ambiguous inbound money lands in `1100` Suspense and is reconciled by ops — never
  silently absorbed or optimistically credited.

## 12. What the ledger deliberately is *not*

- **Not a log.** A log records what an app did; this ledger *is* what the app did to
  money.
- **Not eventually consistent with a "real" balance elsewhere.** There is no
  elsewhere (**P-1**).
- **Not extensible by widening the door.** New products are new *recipes* through
  the same door, new rails are *adapters*, new currencies are *data*. The door does
  not widen.

## 13. The history that produced this design

Wepl once tracked money in three places — mutable balance columns, a single-entry
`LedgerEntry` shadow, and a dormant double-entry core — and ran a nightly job just
to *detect* the drift between them (the
[2026-06 audit](../../audit/2026-06-architecture-audit.md)). Phase 0 made the
double-entry core authoritative and deleted the other two. This chapter is the
settled result. The lesson, paid for in real engineering time, is **P-1**: two
sources of truth for money is not a state you manage — it is a bug you have not yet
been bitten by.

---

*Continue to [Governance Architecture](13-governance-architecture.md) and
[Identity Architecture](14-identity-architecture.md). For the mechanics of getting
money onto the rails, see
[Payments Architecture](../architecture/27-payments-architecture.md).*
