# WEPL — Architecture & Financial-OS Readiness Audit

- **Date:** 2026-06-19
- **Scope:** Full backend (`backend/apps/*`, `config/*`), infra (`render.yaml`,
  `Dockerfile`, `docker-compose.yml`), reviewed as wired at runtime — not as
  docstrings aspire.
- **Verdict headline:** Well-engineered community-finance app (Stage 2→3) with a
  correct but **dormant** double-entry core. Overall **5.0/10** on the
  trajectory-to-Financial-OS scale.

This file is the captured record behind the [roadmap](../roadmap/README.md).

## Central finding — three sources of truth for money
1. **Mutable balance columns** (de-facto truth used by business logic):
   `Contribution.current_amount`, `WelfareFund.balance`, `SharesFund.total_pool`,
   `ContributionAccount`, `ContributionBalance`.
2. **Legacy single-entry ledger:** `LedgerEntry` + `apps/ledger/writer.py` +
   `apps/ledger/queries.py`, reconciled nightly against (1).
3. **Double-entry core:** `Account`/`JournalEntry`/`JournalLine`/`AccountBalance`
   (`posting.py`, `coa.py`, `balances.py`) — correct, tested, **imported by nothing
   outside `apps/ledger/`**.

The authoritative representation is the weakest (1). The system is
*mutable-field-first with a single-entry shadow*, not ledger-first.

## Scorecard
| Dimension | Score |
|-----------|-------|
| Application craftsmanship | 7.5/10 |
| Financial core *as wired* | 4/10 |
| Financial core *design intent* (dormant core) | 7/10 |
| Enterprise/BaaS readiness | 2.5/10 |
| **Overall (trajectory to Financial OS)** | **5.0/10** |

## Strengths (genuine, rare at this stage)
- State machines with optimistic locking (`UPDATE WHERE state=current`).
- Idempotency keys on all money paths; immutable ledger rows; reversal handling.
- DB-level deferred trigger enforcing `Σdebit == Σcredit` (migration `0003`).
- Rebuildable `AccountBalance` projection + reconciliation/recovery jobs.
- Domain event bus, custom DRF exception handler, throttling, Celery queue routing.
- Centralised `FinancialPermissions`; sophisticated quorum/deadlock governance.

## Top risks
| Risk | Severity | Where |
|------|----------|-------|
| Triple source of truth → drift | High | balances vs `LedgerEntry` vs journals |
| Double-entry core unintegrated | High | `apps/ledger/posting.py` (unused) |
| `STAGING_OTP_BYPASS=true` in prod env | High | `render.yaml` |
| KYC media on ephemeral dyno disk | High | `production.py` MEDIA (no S3/R2) |
| Tests not green / not CI-enforced | High | 45 errors/4 failures; default runner finds 0 tests |
| Celery folded into web dyno | Medium | `render.yaml` (free plan) |
| In-process event signals (lossy) | Medium | `apps/core/events.py` |
| No limits/risk/AML | Medium | absent |
| Money precision mismatch (2dp vs 4dp) | Medium | legacy vs core |
| God modules | Medium | `contributions/services.py` (2,012 lines), `models.py` (849) |

## Stage placement
Late **Stage 2**, reaching into **Stage 3**: Stage-3 feature breadth (welfare,
ROSCA, shares, advances, standing orders, governance) on a Stage-2 financial core.

## Recommended response
Captured as the phased [roadmap](../roadmap/README.md). The defining move is
**Phase 0**: make the double-entry core authoritative, route all money through
`post_journal()`, and delete the legacy ledger + mutable balances — additive-first,
behind a green test gate.
