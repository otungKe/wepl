# Phase 6 — Multi-Tenancy

**Status:** 🔴 Not started · **Depends on:** Phases 0, 3, 4

## Objective
Introduce a first-class tenant boundary so WEPL can host multiple institutions with
isolation, per-tenant configuration, limits, and reporting — the precondition for
BaaS (Phase 7).

## Decision to make early (ADR)
Isolation model: **shared schema + `tenant_id` everywhere** (with row-level
security) vs **schema-per-tenant** vs **database-per-tenant**. Recommend starting
shared-schema + RLS; document trade-offs in a Phase-6 ADR before building.

## Work items
- **P6-01** Tenant model + `tenant_id` threaded through all financial tables
  (accounts, journals, lines). Thread the column from Phase 0 onward to avoid a
  later backfill.
- **P6-02** Postgres Row-Level Security policies keyed on tenant.
- **P6-03** Tenant-scoped chart of accounts + per-tenant config/limits.
- **P6-04** Tenant-aware auth, admin, and reporting.
- **P6-05** Cross-tenant access audit + guardrails.

## Acceptance criteria
- No query can read another tenant's financial data (RLS-proven test).
- Trial balance and reports are correct per tenant.

## Exit criteria
- [ ] Hard tenant isolation verified; per-tenant configuration live.
