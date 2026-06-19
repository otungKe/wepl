# Phase 7 — Banking-as-a-Service

**Status:** 🔴 Not started · **Depends on:** Phases 1, 3, 6

## Objective
Expose WEPL's ledger, wallet, and payment capabilities as a product other
businesses build on: public API, API-key/OAuth client model, outbound webhooks,
and a true sandbox.

## Work items
- **P7-01** Versioned public API (OpenAPI schema, deprecation policy) — distinct
  from the internal mobile API.
- **P7-02** API client model: keys/secrets, scopes, rate limits, rotation.
- **P7-03** Outbound webhooks (built on the Phase 2 outbox) with signing + retries.
- **P7-04** Sandbox environment with fake rails (Phase 1 fake provider) + test data.
- **P7-05** Developer docs, SDKs, idempotency-key contract for all write endpoints.
- **P7-06** Usage metering + billing hooks.

## Acceptance criteria
- A third party can open a wallet, move money, and receive signed webhooks in sandbox
  without touching internal code.
- Public API is versioned and backward-compatible within a major version.

## Exit criteria
- [ ] Externally consumable, documented, sandboxed BaaS API.
