# Architecture Decision Records (ADRs)

Short, immutable records of significant architectural decisions: the context, the
decision, and its consequences. ADRs are **append-only** — to change a decision,
add a new ADR that supersedes the old one (note it in both).

## Index

| # | Title | Status |
|---|-------|--------|
| [0001](0001-ledger-first-double-entry.md) | Ledger-first, double-entry as the single book of record | Accepted |
| [0002](0002-remove-legacy-ledger-and-mutable-balances.md) | Remove the legacy single-entry ledger and mutable balance fields | Accepted |
| [0003](0003-money-representation.md) | Money representation: Decimal(20,4) + Money value object + currency | Accepted |
| [0004](0004-post-journal-single-entrypoint.md) | `post_journal()` is the single money-mutation entrypoint | Accepted |
| [0005](0005-payment-provider-abstraction.md) | Payment provider port/adapter abstraction | Proposed |
| [0006](0006-transactional-outbox.md) | Transactional outbox for durable domain events | Proposed |
| [0007](0007-controls-at-posting-chokepoint.md) | Limits & risk controls live at the posting chokepoint | Proposed |
| [0023](0023-identity-verification-provider.md) | Identity-verification provider port/adapter | Accepted |
| [0024](0024-fee-and-tax-postings.md) | Fee, excise-duty and withholding postings | Proposed |

## Template

```markdown
# ADR-NNNN: <title>
- **Status:** Proposed | Accepted | Superseded by ADR-XXXX
- **Date:** YYYY-MM-DD
- **Deciders:** <names>

## Context
What is the situation and the forces at play?

## Decision
What we are doing, stated plainly.

## Consequences
Positive, negative, and follow-on effects. What becomes easier/harder.

## Alternatives considered
Options rejected and why.
```
