# ADR-0026: Public BaaS API surface & versioning

- **Status:** Proposed
- **Date:** 2026-07-11
- **Deciders:** Architecture review
- **Phase:** 7 (Banking-as-a-Service) · work items P7-01, P7-05

## Context
Phase 7 exposes Wepl's ledger/wallet/payments as a product: third parties provision
accounts and move money on their tenant's ledger via a public API, receiving
outbound webhooks. This is the [Vision](../handbook/product/01-vision.md)'s endgame —
"the Financial OS others run on."

Unlike the internal customer/ops APIs (which ship in lockstep with our own clients),
a **public API is a promise to external integrators who upgrade on their own
schedule.** A breaking change we make casually becomes their production outage. We
need an explicit versioning and compatibility policy *before* the first external call,
not after. The internal API already standardizes on DRF + a uniform error envelope +
OpenAPI via drf-spectacular ([ADR-0021](0021-api-conventions.md)); the public surface
should extend those conventions, not invent new ones.

## Decision
1. **A distinct public surface** at a versioned prefix (`/api/baas/v1/...`), separate
   from `/api/` (customer) and `/api/ops/` (staff). Audiences with different authority
   get different doors (mirrors P-12).
2. **Explicit, path-based major versioning** (`/v1`, `/v2`). Only breaking changes bump
   the major; additive changes (new fields, new endpoints) do not. Clients pin a major
   version.
3. **OpenAPI is the contract.** The drf-spectacular schema for the public surface is
   the single source of truth and the source of generated client SDKs and the sandbox
   — hand-written docs are forbidden (they drift). "The schema is generated, not
   written" (mirrors [API Architecture](../handbook/architecture/23-api-architecture.md)).
4. **A published deprecation policy:** a deprecated major version is announced, dual-run
   for a defined support window, emits `Deprecation`/`Sunset` headers, then retired.
5. **Every public endpoint is tenant-scoped** ([ADR-0008](0008-multi-tenancy.md)) and
   money still moves only through `post_journal()` ([ADR-0004](0004-post-journal-single-entrypoint.md)).
   The public API is just another caller of the one door; it relaxes no invariant.
6. **The idempotency-key contract is first-class and documented** — every money-moving
   public request carries a client idempotency key that maps to the ledger's
   `idempotency_key`, so integrator retries are safe end-to-end.

## Consequences
- **+** External integrators get a stable, self-describing, safely-versioned contract;
  SDKs and sandbox derive from the same schema.
- **+** The public surface inherits the internal conventions (errors, pagination,
  honest status codes, idempotency) rather than forking them.
- **−** A real compatibility burden: we must run and support deprecated majors for the
  window, and resist breaking changes.
- **−** Requires per-surface schema tooling and SDK generation in CI.

## Alternatives considered
- **Expose the internal `/api/` directly to third parties:** rejected — it evolves
  with our clients and has no compatibility guarantee; it would freeze internal
  velocity or break integrators.
- **Header/media-type versioning instead of path:** rejected for the public surface —
  path versioning is the most legible to external integrators and simplest to route
  and cache; revisit only if fine-grained content negotiation is genuinely needed.
- **No versioning ("we'll be careful"):** rejected — an unversioned public money API is
  a promise you will eventually break silently.
