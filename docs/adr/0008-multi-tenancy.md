# ADR-0008: Multi-tenancy via shared schema + `tenant_id` (+ Postgres RLS)

- **Status:** Accepted & implemented (P6-01→05: tenant model + dimension, RLS
  isolation, per-request enforcement, per-tenant CoA/limits, cross-tenant audit;
  `Community.tenant` NOT NULL). Schema/DB-per-tenant remains a future option.
- **Date:** 2026-06-22
- **Phase:** 6 (depends on ADR-0001/0004; Phases 0, 3, 4)

## Context
WEPL must host multiple institutions (SACCOs, chamas-at-scale, future BaaS
clients) with isolation, per-tenant configuration/limits, and per-tenant
reporting. The business root for a tenant is the `Community` (a SACCO maps to one
or more communities); financial data hangs off communities/funds and ultimately
off the ledger (`Account` / `JournalEntry` / `JournalLine`).

Three isolation models were considered:
1. **Shared schema + `tenant_id` on every row** (optionally with Postgres
   Row-Level Security).
2. **Schema-per-tenant.**
3. **Database-per-tenant.**

## Decision
**Shared schema + `tenant_id`**, with **Postgres Row-Level Security (RLS)** as the
defence-in-depth enforcement layer. A `Tenant` row is the boundary; financial and
business tables carry a nullable-then-mandatory `tenant` FK. Tenant is resolved
from the owning aggregate (Community → Tenant) and, at request time, from the
authenticated user's tenant.

Isolation is enforced in two layers:
- **Application layer (now):** tenant-scoped querysets/reporting filters and a
  resolved "current tenant" on the request.
- **Database layer (next):** RLS policies keyed on `current_setting('app.tenant_id')`,
  set per request/connection, with `FORCE ROW LEVEL SECURITY` so even the table
  owner is constrained — making cross-tenant reads impossible regardless of an
  application bug.

## Why not schema/DB-per-tenant
- The ledger's invariants, reconciliation, and reporting are written once against
  one schema; per-schema/DB multiplies migrations, connection management, and
  cross-tenant ops (platform trial balance, BaaS) by N.
- Shared-schema + RLS gives strong isolation with one schema to evolve. Schema/DB
  isolation can be layered later for a specific high-compliance tenant without
  changing application code.

## Consequences
- **+** One schema/migration path; platform-wide reporting is trivial; per-tenant
  reporting is a filter; RLS provides a hard backstop.
- **+** `tenant_id` threaded from here forward avoids a painful later backfill
  (Phase-0 guidance).
- **−** Every financial query must be tenant-correct; RLS session management must
  be bullet-proof (set per request, reset on connection reuse) — this is why RLS
  is delivered as its own carefully-tested increment after the column foundation.
- **−** A null `tenant` means "platform/shared" (e.g. global GL accounts); code
  must treat null deliberately, not accidentally.

## Rollout (additive before destructive)
1. **Foundation (this increment):** `Tenant` model; nullable `tenant` FK on
   `Community`, `Account`, `FinancialTransaction`; backfill to a default tenant;
   tenant resolution helpers; tenant-scoped reporting.
2. Thread `tenant` into account/FT creation (per-tenant chart of accounts, P6-03).
3. RLS policies + per-request session var (P6-02) with an isolation-proof test.
4. Tenant-aware auth/admin + cross-tenant access audit (P6-04/05).
5. Make `tenant` non-nullable once fully backfilled and wired.
