# Phase 6 — Multi-Tenancy

**Status:** 🟢 Done · **Depends on:** Phases 0, 3, 4 · **ADR:** [0008](../adr/0008-multi-tenancy.md)

Isolation model (ADR-0008): **shared schema + `tenant_id` + Postgres RLS**. Tenant
model + dimension, RLS isolation, per-request enforcement, per-tenant chart of
accounts/limits, and cross-tenant audit are all in place.

> Operational requirement: RLS only enforces when `wepl-api` connects with a
> **non-superuser** Postgres role (superusers bypass RLS). Confirm the deploy role.

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
- [x] **P6-02** Postgres Row-Level Security on the tenant-scoped financial tables
  (`ledger_account`, `ledger_financialtransaction`): `ENABLE` + `FORCE ROW LEVEL
  SECURITY` with a policy keyed on the `app.tenant_id` session GUC. Helpers
  (`apps/tenants/rls.py`: `set_current_tenant` / `clear_current_tenant` /
  `tenant_context`). Proven by test (a non-superuser `SET ROLE` cannot read
  another tenant's rows even via raw SQL). **Deploy note:** RLS is bypassed by
  superusers — run the app with a NON-superuser DB role for it to bite.
  *Remaining:* set `app.tenant_id` per authenticated request (lands with P6-04,
  since the app uses JWT — tenant comes from the user, resolved in DRF, not the
  Django session middleware).
- [x] **P6-03** Tenant-scoped chart of accounts + per-tenant config/limits.
  Member sub-ledger accounts (`coa.member_fund_account`) and `FinancialTransaction`
  rows are stamped with the fund's community tenant on creation (GL parents stay
  shared/null). `LimitRule` gained a nullable `tenant` FK — global rules apply to
  all tenants, tenant-scoped rules only to that tenant; the controls engine filters
  by the movement's tenant. `Tenant.config` JSON is the seam for further per-tenant
  settings.
- [x] **P6-04** Tenant-aware auth + reporting. `TenantJWTAuthentication` sets the
  per-request RLS context (`app.tenant_id`) for member users; `TenantRLSMiddleware`
  resets it after every request (safe under connection pooling). Platform staff /
  superusers are intentionally NOT pinned (cross-tenant operators; Django admin
  stays platform-wide). Reporting functions + the staff reports API accept
  `tenant_id`. *Remaining:* per-tenant admin **operator** scoping (a non-staff
  tenant-admin role) is a follow-up.
- [x] **P6-05** Cross-tenant access audit + guardrails. `guards.guard_tenant`
  refuses + audits (`CrossTenantAccessAttempt`) access to another tenant's
  aggregate when a request is pinned to a tenant (wired into the community detail
  view; system/staff contexts unrestricted by design). `Community.tenant` is now
  NOT NULL (backfilled + stamped on create). `Account.tenant` /
  `FinancialTransaction.tenant` remain nullable **by design** — null = shared GL
  / system movement, which the RLS policy treats as globally visible.

## What landed (foundation)
- `apps/tenants`: `Tenant` model, `default_tenant()`, `tenant_for_user()`,
  `tenant_for_community()` resolution helpers, admin.
- Nullable `tenant` FK on `Community` / `Account` / `FinancialTransaction`,
  backfilled to a `default` tenant (additive — ADR-0008 rollout step 1).
- Reporting + reports API are tenant-filterable (`?tenant_id=`); proven isolated
  by test (one tenant's report never reads another's lines).

## Acceptance criteria
- [x] No query can read another tenant's financial data — **RLS-proven test**
  (`apps/tenants/tests.RowLevelSecurityTests`): a non-superuser role with
  `app.tenant_id` set cannot read another tenant's rows, even via raw SQL.
  *Caveat:* requires a non-superuser DB role in production; per-request context
  wiring lands with P6-04.
- [x] Trial balance and reports are correct per tenant.

## Exit criteria
- [x] Hard tenant isolation verified (RLS-proven test, non-superuser role);
  per-tenant configuration live (per-tenant limit rules + `Tenant.config`).
