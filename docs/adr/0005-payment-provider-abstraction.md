# ADR-0005: Payment provider port/adapter abstraction

- **Status:** Accepted (implemented — Phase 1, epic #5; `MpesaProvider` = adapter #1, `FakeProvider` in CI)
- **Date:** 2026-06-19 (accepted 2026-07-11)
- **Phase:** 1

## Context
M-Pesa/Daraja specifics (STK push, B2C, transaction-status query, security
credential, Safaricom field names) are spread across `apps/mpesa/services.py`,
`apps/ledger/tasks.py`, and views. Adding any new rail today means editing financial
logic and risks regressing money paths. It also makes money-path tests require
network/sandbox.

## Decision
Introduce a `PaymentProvider` port with a normalised contract
(`initiate_collection`, `initiate_payout`, `query_status`, normalised
callback→event mapping). `MpesaAdapter` is the first implementation; a
`FakeProvider` enables hermetic tests. The ledger posting path consumes only the
normalised, rail-agnostic event.

## Consequences
- **+** New rails (card/bank/other MMO) add an adapter, not edits to finance code.
- **+** Hermetic CI for money paths via the fake provider.
- **−** One indirection layer; an upfront refactor of existing M-Pesa code.

## Alternatives considered
- *Keep M-Pesa concrete until a second rail is needed:* rejected — retrofitting the
  seam later is far more expensive and risky than extracting it once money paths are
  already being touched in Phase 0/1.
