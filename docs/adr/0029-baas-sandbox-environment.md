# ADR-0029: BaaS sandbox environment

- **Status:** Proposed
- **Date:** 2026-07-11
- **Deciders:** Architecture review
- **Phase:** 7 (Banking-as-a-Service) · work item P7-04
- **Depends on:** [ADR-0005](0005-payment-provider-abstraction.md) (payment port), [ADR-0023](0023-identity-verification-provider.md) (identity port), [ADR-0027](0027-baas-api-key-authentication.md) (tenants/keys)

## Context
Integrators must be able to build and test against Wepl **without touching real
money or real people's identities.** They need realistic behaviour — STK-push-style
collections, payouts, KYC decisions, webhooks — that is fully deterministic and
consequence-free. The exit criterion for Phase 7 is literally "a third party can open a
wallet, move money, and receive signed webhooks *in sandbox*."

Wepl already has the two seams this requires: the payment rail is behind a port with a
`FakeProvider` ([ADR-0005](0005-payment-provider-abstraction.md)), and identity
verification is behind a port with a `FakeProvider` ([ADR-0023](0023-identity-verification-provider.md)).
These fakes already back the test suite. The sandbox is those same fakes, exposed as a
product surface behind a tenant.

## Decision
1. **Sandbox = fake providers behind a tenant.** A sandbox tenant resolves the payment
   and identity ports to their `FakeProvider` implementations. Everything else — the
   ledger, `post_journal()`, the outbox, webhooks, the public API — is the **real code
   path**. Only the outermost rails/identity adapters are fake.
2. **Deterministic, controllable outcomes.** The fakes expose test controls (force a
   collection success/failure/timeout, approve/reject a KYC case, trigger a specific
   webhook) so integrators can exercise every branch, including the failure paths that
   *are the product* (P-16).
3. **Hard isolation from production.** Sandbox tenants and their data are isolated from
   live tenants ([ADR-0008](0008-multi-tenancy.md)); sandbox API keys
   ([ADR-0027](0027-baas-api-key-authentication.md)) cannot address production, and
   sandbox money never touches a real rail. The isolation is the same boundary that
   protects live tenants from each other — reused, not re-invented.
4. **Same schema, same versioning, same webhooks.** The sandbox serves the identical
   OpenAPI contract and version ([ADR-0026](0026-public-baas-api-and-versioning.md)) and
   emits real, signed webhooks ([ADR-0028](0028-outbound-webhooks.md)) — so "works in
   sandbox" is a meaningful predicate for "works in production."
5. **Seedable test data** for onboarding (sample members, funds, a starting float) so
   an integrator is productive in minutes.

## Consequences
- **+** Integrators build against realistic, real-code-path behaviour with zero real-
  money risk; the failure branches are exercisable.
- **+** The sandbox is *almost free*: it reuses the existing `FakeProvider`s, the real
  ledger, the real tenant isolation, and the real webhook engine. It is a configuration
  of production, not a separate stack.
- **+** It doubles as our own integration-test and demo environment.
- **−** We must guarantee the sandbox and production paths stay identical except at the
  fake seams — divergence would make "works in sandbox" a lie. This is a standing test
  obligation.
- **−** Sandbox abuse (resource use, as a free compute surface) needs rate limits and
  data-retention/reset policies.

## Alternatives considered
- **A wholly separate sandbox codebase/stack:** rejected — it would drift from
  production, and "works in sandbox" would stop predicting "works in production."
- **Let integrators test against production with tiny real amounts:** rejected — real
  money, real KYC, real rail cost, and real blast radius for a *testing* activity.
- **Mock the whole API (not just the rails):** rejected — mocking the ledger/outbox
  would mean integrators never exercise the real behaviour (idempotency, balancing,
  webhook timing) they must build against.
