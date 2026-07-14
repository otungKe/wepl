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
| [0005](0005-payment-provider-abstraction.md) | Payment provider port/adapter abstraction | Accepted |
| [0006](0006-transactional-outbox.md) | Transactional outbox for durable domain events | Accepted |
| [0007](0007-controls-at-posting-chokepoint.md) | Limits & risk controls live at the posting chokepoint | Accepted |
| [0008](0008-multi-tenancy.md) | Multi-tenancy via shared schema + `tenant_id` (+ Postgres RLS) | Accepted |
| [0009](0009-centralized-authorization-policy.md) | Centralized authorization policy layer | Accepted |
| [0010](0010-session-registry-and-token-revocation.md) | Device/session registry & on-demand token revocation | Accepted |
| [0011](0011-community-ownership-and-lifecycle.md) | Community ownership transfer & the last-admin invariant | Accepted |
| [0012](0012-chat-scaling.md) | Chat data model & real-time scaling | Accepted |
| [0013](0013-contributions-module-split.md) | Contributions module split (god-service decomposition) | Accepted |
| [0014](0014-payment-aggregate-and-reconciliation.md) | Provider-agnostic Payment aggregate & reconciliation | Accepted |
| [0015](0015-multi-channel-notification-delivery.md) | Multi-channel notification delivery & dead-letter | Accepted |
| [0016](0016-activity-feed-architecture.md) | Activity feed — typed events, visibility & fan-out model | Accepted |
| [0017](0017-search-architecture.md) | Search architecture | Accepted |
| [0018](0018-file-storage-and-media-pipeline.md) | File storage & media pipeline | Accepted |
| [0019](0019-append-only-audit-log.md) | Append-only audit log | Accepted |
| [0020](0020-observability-standard.md) | Observability standard — structured logging & health probes | Accepted |
| [0021](0021-api-conventions.md) | API conventions — versioning, OpenAPI schema, pagination default | Accepted |
| [0022](0022-two-tier-access-model.md) | Two-tier access model (KYC-gated full access) | Accepted |
| [0023](0023-identity-verification-provider.md) | Identity-verification provider port/adapter | Accepted |
| [0024](0024-fee-and-tax-postings.md) | Fee, excise-duty and withholding postings | Proposed |
| [0025](0025-financial-account-and-pool-identity.md) | Financial-account identity and pools as first-class accounts | Accepted |
| [0026](0026-organization-and-program-spine.md) | Organization spine — every participant is an Organization | Accepted |

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
