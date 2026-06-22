# Phase 6 — Multi-Tenancy

**Status:** 🟡 In progress (foundation) · **Depends on:** Phases 0, 3, 4 · **ADR:** [0008](../adr/0008-multi-tenancy.md)

Isolation model decided in ADR-0008: **shared schema + `tenant_id` + Postgres RLS**.
This increment lands the additive foundation; RLS and full threading follow.

## Objective
Introduce a first-class tenant boundary so WEPL can host multiple institutions with
isolation, per-tenant configuration, limits, and reporting — the precondition for
BaaS (Phase 7).

## Work items
- [~] **P6-01** `Tenant` model (`apps/tenants`) + `tenant` FK on `Community`,
  `Account`, `FinancialTransaction`; default tenant + backfill migration so every
  existing row is tenant-stamped. New communities are stamped on create.
  *Remaining:* thread `tenant` onto member sub-ledger accounts at creation and
  onto `JournalEntry`/`JournalLine`, then make the column NOT NULL.
- [ ] **P6-02** Postgres Row-Level Security policies keyed on
  `current_setting('app.tenant_id')` with `FORCE ROW LEVEL SECURITY` + per-request
  session var (the hard DB-level isolation). Designed in ADR-0008; next increment.
- [ ] **P6-03** Tenant-scoped chart of accounts + per-tenant config/limits
  (`Tenant.config` JSON is the seam; limits engine to read tenant config).
- [~] **P6-04** Tenant-aware reporting — every reporting function + the staff
  reports API accept `tenant_id` (per-tenant trial balance / balance sheet /
  income statement). *Remaining:* tenant-aware auth + admin scoping.
- [ ] **P6-05** Cross-tenant access audit + guardrails.

## What landed (foundation)
- `apps/tenants`: `Tenant` model, `default_tenant()`, `tenant_for_user()`,
  `tenant_for_community()` resolution helpers, admin.
- Nullable `tenant` FK on `Community` / `Account` / `FinancialTransaction`,
  backfilled to a `default` tenant (additive — ADR-0008 rollout step 1).
- Reporting + reports API are tenant-filterable (`?tenant_id=`); proven isolated
  by test (one tenant's report never reads another's lines).

## Acceptance criteria
- [ ] No query can read another tenant's financial data (RLS-proven test) — **P6-02**.
  *Today:* application-level scoping is proven isolated in tests; DB-level RLS pending.
- [x] Trial balance and reports are correct per tenant.

## Exit criteria
- [ ] Hard tenant isolation verified (RLS); per-tenant configuration live.
