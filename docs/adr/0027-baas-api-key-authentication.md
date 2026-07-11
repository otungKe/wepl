# ADR-0027: Per-tenant API-key authentication & authorization for BaaS

- **Status:** Proposed
- **Date:** 2026-07-11
- **Deciders:** Architecture review
- **Phase:** 7 (Banking-as-a-Service) · work item P7-02
- **Depends on:** [ADR-0008](0008-multi-tenancy.md) (tenancy), [ADR-0026](0026-public-baas-api-and-versioning.md) (surface)

## Context
The public BaaS API ([ADR-0026](0026-public-baas-api-and-versioning.md)) is called by
*machines* (integrator backends), not by humans with phones or corporate emails. So it
needs a third authentication regime, distinct from the two we already have —
customer phone+OTP JWT and staff email+password `type:"ops"` JWT
([Identity Architecture](../handbook/domain/14-identity-architecture.md), P-12).

The defining risk of BaaS is **cross-tenant leakage** (handbook risk R11): one
integrator reading or moving another's money. Auth is the first line of defence, so
credentials must be *intrinsically* tenant-bound — it must be impossible to present a
credential that resolves to the wrong tenant.

## Decision
1. **API keys, scoped to exactly one tenant.** Each key belongs to one `Tenant`; every
   request authenticated by that key is executed *only* against that tenant's data.
   Tenant scoping is a property of the credential, not a request parameter the caller
   chooses.
2. **Keys carry scopes** (capabilities) — e.g. `accounts:read`, `payments:write`,
   `webhooks:manage` — enforced server-side, mirroring the staff capability model
   ([ADR-0009](0009-centralized-authorization-policy.md)). Least privilege by default.
3. **Keys are stored hashed**, shown once at creation, and support **rotation** (issue
   new, overlap, revoke old) and immediate **revocation**. No key is ever recoverable
   in plaintext after creation.
4. **A secret/publishable split** where useful (publishable for client-side identify
   operations, secret for money movement) so integrators don't ship money-moving
   secrets to browsers/apps.
5. **Per-key rate limits and throttles** ([ADR-0021](0021-api-conventions.md)), which
   **fail open on a cache outage** consistent with the platform's honest-degradation
   posture (P-16) but are bounded so an outage can't exhaust resources.
6. **Every key action is audited** ([ADR-0019](0019-append-only-audit-log.md)): key
   creation, rotation, revocation, and money movement are recorded, non-repudiably,
   per tenant.
7. **This regime is wholly separate** from customer and staff auth — separate
   middleware, separate token type, no shared code path that could cross the streams
   (P-12).

## Consequences
- **+** Tenant isolation is enforced at the credential itself — the strongest place to
  put it. A key *cannot* address another tenant.
- **+** Scopes + rotation + revocation + audit give integrators (and us) real
  operational control and a forensic trail.
- **−** Key lifecycle management (issuance UI/API, rotation UX, leak response) is real
  surface area to build and document.
- **−** A third auth regime to maintain and security-review alongside the two existing
  ones.

## Alternatives considered
- **Reuse customer/staff JWTs for BaaS:** rejected — those identify humans, not
  tenant-scoped machine clients, and mixing them risks the exact escalation P-12
  forbids.
- **OAuth2 client-credentials from day one:** deferred — API keys are simpler for
  early integrators and cover the need; OAuth2 client-credentials can be added later as
  an alternative grant without changing the tenant-scoping model.
- **Tenant chosen per-request (header/param) with a global key:** rejected outright —
  it makes cross-tenant access a typo away and defeats the isolation guarantee.
