---
name: wepl-tenancy
description: How tenant isolation actually works in WEPL — the app.tenant_id
  Postgres GUC, where it is set and cleared, which tables are under RLS and
  which are not, Celery task hygiene, the cross-tenant guard, and how much of
  Phase 6 is a live boundary versus a seam. Use when touching apps/tenants,
  adding a tenant-scoped model or migration, writing a Celery task or a
  consumer that reads tenant data, or reasoning about cross-tenant exposure.
---

# WEPL tenancy

Shared schema + a `tenant_id` column + Postgres Row-Level Security (ADR-0008).
`docs/roadmap/PHASE-6-multi-tenancy.md` is marked 🟢 Done — read that as "the
mechanism landed", not "the boundary is live".

> **Framing call taken 2026-09-21, correct it if you disagree.** This skill
> treats tenancy as a **staged seam, not a live boundary**. Every mechanism is
> built and proved — the GUC, the policies, the Celery hooks, the cross-tenant
> guard — but `tenant_for_user()` returns the default tenant for everyone, so
> nothing is actually separated yet. The practical consequence is the rule in
> "Rules to preserve": keep the seam correct on every new table and every new
> task, because the day a real resolver lands, everything written before it has
> to already be right. Do not use "tenancy is not live" as a reason to skip the
> policy, the guard or the `tenant_id` column — and do not claim isolation as a
> security property to anyone outside this repo.

## How context flows

1. **Set** — `apps/tenants/auth.py::pin_request_tenant` pins the GUC right
   after the user is resolved: `SELECT set_config('app.tenant_id', %s, false)`.
   It is **not** named in `DEFAULT_AUTHENTICATION_CLASSES` (that is plain
   `apps.users.auth.SessionJWTAuthentication`); `TenantsConfig.ready()` registers
   it into `apps/core/request_context.py` and the authenticator calls it there,
   at the same moment the old tenant-aware subclass ran (ADR-0033). **Deleting
   that one `ready()` line would silently leave every request in the permissive
   system context** — `TenantPinRegistrationTests` exists to catch that.
2. **Cleared** — `apps/tenants/middleware.py::TenantRLSMiddleware` (last in
   `MIDDLEWARE`) clears it in a `finally` on every request. Connections are
   pooled (`CONN_MAX_AGE=60`), so this is not optional.
3. **Celery** — `apps/tenants/celery_hooks.py` clears on **both** `task_prerun`
   and `task_postrun`. Tasks therefore start in the permissive *system* context
   and never leak a tenant onto the next task.
4. **Scoped work** — `with tenant_context(tenant_id):` (`apps/tenants/rls.py`).
   Used by `apps/conversations/consumers.py`.

**Staff and superusers are deliberately NOT pinned** — operators work across
tenants and the Django admin must stay platform-wide.

## The RLS policy

```sql
USING / WITH CHECK (
  NULLIF(current_setting('app.tenant_id', true), '') IS NULL   -- system context
  OR tenant_id IS NULL                                          -- shared row
  OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::integer
)
```

`ENABLE` + **`FORCE`** on nine tables:
`ledger_account`, `ledger_financialtransaction` (migration 0003);
`communities_community`, `controls_limitrule`, `payments_paymentintent`,
`audit_auditevent`, `files_storedfile` (0005); `payments_providerevent` (0006);
`organizations_organization` (0007); `organizations_program` (0008).

`FORCE` makes the policy apply to the table owner. **A Postgres superuser still
bypasses RLS** — isolation only bites when the app runs as a non-superuser role.
`apps/tenants/tests.py::RowLevelSecurityTests` proves it by `SET ROLE`-ing to a
freshly created `NOSUPERUSER` probe. `ledger/views.py::TenancyCheckView`
(`IsAdminUser`) reports which tables actually have RLS on, read from `pg_class`.

## What is NOT under RLS — know this before you claim isolation

- **`ledger_journalentry`, `ledger_journalline`, `ledger_accountbalance`.**
  They carry no `tenant_id` and no policy. Isolation covers the *account*
  dimension and FT, not the lines. Raw journal reads are blocked only by the
  application.
- **All contributions funds** (`Contribution`, `WelfareFund`, `SharesFund`,
  and everything hanging off them). ADR-0008 says tables without a `tenant_id`
  inherit tenancy through their Community and stay application-scoped. The
  mechanism meant to cover them is `guards.py::guard_tenant` — which today has
  **exactly one production call site**, `apps/communities/views.py:211`
  (re-verified on `68e8cf6`). Adding the second is real work, not a formality.
- **Everything under `/api/ops/*`.** `StaffAccount` is not a `User`,
  the tenant pin never runs for it, so every ops query runs in the
  permissive system context. Deliberate; protected by capabilities instead.

## `tenant_id IS NULL` means "visible to everyone"

That is right for GL accounts. It is also what you get when resolution fails:
- `coa.py::_tenant_for_fund` swallows every exception and returns `None`.
- `ledger/writer.py::create_fin_transaction` sets `tenant=None` when the fund has
  no community — and `SharesFund.community` / `WelfareFund.community` are both
  nullable.

`Community.tenant`, by contrast, is **NOT NULL** at the database level.

## Tenant resolution is a seam, not a resolver

`apps/tenants/resolve.py::tenant_for_user(user)` **ignores its argument and
returns the default tenant for everyone** (verified on `68e8cf6`). Its docstring
says P6-04 will derive it from institution membership. So today RLS is verified
correct but is not separating anyone: every user resolves to the same tenant id,
so every policy evaluates true for every row.

`tenant_for_community(community)` *is* real — it reads `community.tenant`. The
seam is specifically the **user → tenant** edge.

When the resolver lands, the things that break are the ones this skill lists as
not covered: journal lines, contributions funds, and every ops query. Those are
the work, not the policies.

## Rules to preserve

1. Set the GUC in authentication, clear it in middleware and in both Celery
   hooks. Never set it in a view, a serializer or a service.
2. Staff/superusers stay unpinned. Do not "fix" that.
3. A task that needs one tenant uses `with tenant_context(id):` — never a bare
   `set_current_tenant`.
4. `set_config` is parameterised. Never interpolate a tenant id into SQL.
5. A new tenant-columned table gets a migration adding `ENABLE` + **`FORCE`** +
   `tenant_isolation`, in the shape of `tenants/migrations/0005`, and is added to
   `TenancyCheckView.RLS_TABLES`.
6. A new tenant-owned aggregate *without* a `tenant_id` column calls
   `guard_tenant(resource.tenant_id, request=request, resource_type=…,
   resource_id=…)` at its boundary. Blocked attempts are audited as
   `CrossTenantAccessAttempt`.
7. `apps/tenants/celery_hooks.py` and `apps/tenants/guards.py` are held to
   **≥90 % coverage** in CI.

## Do not assume

- Do not assume `tenant_for_user` is real.
- Do not assume a table is under RLS because it is financial — journals are not.
- Do not assume RLS is active in a given environment; it depends on the DB role.
- Do not assume `guard_tenant` protects a path.
- Do not assume `tenant_id IS NULL` means "platform row" — it may mean
  "resolution failed".
- Do not assume ops endpoints are tenant-scoped.

## Forbidden shortcuts

- Calling `clear_current_tenant()` inside a request to "see more rows".
- Adding a policy without `FORCE`, or with a `USING (true)` escape hatch.
- Running the app as a Postgres superuser and calling tenancy done.
- Setting the GUC before `apply_async` so the task "inherits" the tenant — the
  prerun hook clears it by design.
- Adding a nullable `tenant` FK to a new table and leaving it null by default.

## Key tests

`apps/tenants/tests.py` — `RowLevelSecurityTests` (raw SQL under a NOSUPERUSER
role), `ExtendedRowLevelSecurityTests`, `TenantContextWiringTests`
(member pinned / staff not pinned / middleware resets), `PerTenantChartOfAccountsTests`,
`PerTenantLimitsTests`, `CrossTenantGuardTests`, `TenantScopedReportingTests`.
`apps/conversations/tests_tenant.py` (a `TransactionTestCase`).

**Gaps to know about** (as of `68e8cf6`, 2026-09-21): no RLS *write* test
exercises the `WITH CHECK` clause, though five migrations declare one; no test
enumerates the expected set of RLS tables, so a new tenant-columned table can
ship without a policy and nothing complains; no test asserts `guard_tenant` is
called where ADR-0008 says it should be.
