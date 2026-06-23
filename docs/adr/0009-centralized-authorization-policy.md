# ADR-0009: Centralized authorization policy layer

- **Status:** Accepted (initial implementation in `apps/core/policy.py` + `apps/communities/policies.py`)
- **Date:** 2026-06-23
- **Relates to:** Platform Hardening Review (`docs/review/2026-06-platform-hardening-review.md`), finding #1

## Context

Coarse authentication is consistent and good: `IsActiveSession` gates 81 endpoints on a
valid active-stage JWT. But **fine-grained authorization** — "is this user an admin of *this*
community", "may this user delete it", "can they review *this* join request" — is implemented
as **inline checks scattered across views and services**:

- `communities/views.py`: a `_is_admin()` helper plus repeated `community.created_by_id == request.user.id` checks.
- `communities/services.py`: `assign_role` / `remove_member` / `action_join_request` each re-derive admin/creator status by hand.
- `contributions/views.py`: ~18 inline `is_admin` / `created_by ==` / role comparisons.

This is the platform's single biggest correctness *and* security risk:

- **Untestable in isolation** — authz logic is welded to request handling.
- **Unauditable** — there is no way to answer "what can a treasurer do?" without grepping.
- **IDOR-prone** — the failure mode is the endpoint that simply *forgets* a check; nothing
  structural prevents it. New endpoints re-implement authz from scratch every time.

This is precisely the dispersal problem ADR-0004/0007 removed for money (single chokepoint).
Authorization deserves the same treatment.

## Decision

Introduce a **centralized, declarative authorization policy layer**.

1. **`apps/core/policy.py`** — a tiny, dependency-free engine:
   - `can(actor, action, resource) -> bool` — never raises (use in serializers/branching).
   - `require(actor, action, resource)` — raises `PermissionDenied` (use at the boundary).
   - Resource types register a **resolver** via `@policy("<resource_type>")`. The action
     string is namespaced (`"community.update"`), and its prefix selects the resolver.
   - Superusers bypass (platform operators); unauthenticated actors are always denied.

2. **Per-resource capability matrices** (e.g. `apps/communities/policies.py`) express authz
   **declaratively** as a role→rank hierarchy + a minimum-rank-per-action table. Role checks
   become data, not control flow.

3. **Call sites change from inline checks to one line**: `require(user, "community.update", community)`.
   Role math disappears from views and services.

The layer raises Django's `PermissionDenied`, which the existing
`core.exceptions.custom_exception_handler` already maps to a clean `403` — so the policy module
stays free of DRF/HTTP coupling and is usable from services, consumers, and tasks alike.

## Consequences

- **+** Authorization is centralized, declarative, reusable, and **unit-testable** without HTTP.
- **+** The capability matrix is a single auditable source of truth ("what can each role do").
- **+** New endpoints opt in with one `require(...)` call; forgetting it is now conspicuous.
- **+** Same engine extends to `contributions`, `conversations`, `notifications`, files, etc.
- **−** A new indirection to learn; mitigated by the matrix being plain data and the API being two functions.
- **−** Resolver registration must run at startup (done in each app's `AppConfig.ready()`).

## Alternatives considered

- **DRF object-level permissions (`has_object_permission`).** Rejected as the *primary*
  mechanism: the codebase uses `APIView` + manual `get_object_or_404`, so DRF's object
  permission lifecycle doesn't fire uniformly, and it can't be reused from services/consumers.
  Thin DRF permission classes may still delegate to `policy.can` where ViewSets are used.
- **Django's built-in permissions / `django-guardian` (per-object).** Rejected for now:
  row-level grant tables are heavyweight for a role-derived model and add write load; the
  capability matrix derives permissions from membership role with zero extra storage.
- **Status quo (inline checks).** Rejected — the dispersal/IDOR problem this ADR exists to fix.

## Rollout

Incremental, one app at a time, each migration shipping with tests:
1. `communities` (this ADR's reference implementation) — **done**.
2. `contributions` (highest inline-check count) — **done**. The pre-existing
   `ledger.permissions.FinancialPermissions` helper became the *implementation*
   behind the registered `contribution` resolver, so services already using it
   are on the centralized layer; the inline `CommunityMembership.objects.filter(...)`
   checks duplicated across the views were migrated to `can()`/`require()`, and a
   `community.finance.manage` capability (admins + treasurers) was added.
3. `conversations`, `notifications`, then the rest.
