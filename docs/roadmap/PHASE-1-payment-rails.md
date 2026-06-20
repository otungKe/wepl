# Phase 1 — Payment Rail Abstraction

**Status:** 🟡 In progress (PR #16) · **Depends on:** Phase 0 · **ADR:** [0005](../adr/0005-payment-provider-abstraction.md)

## Objective
Decouple money *movement* from *rails*. Today M-Pesa Daraja calls are concrete in
`apps/mpesa/services.py`, `apps/ledger/tasks.py`, and views. Introduce a
`PaymentProvider` port so a new rail (card, bank, another mobile-money operator)
can be added without touching financial logic.

## Work items
- **P1-01** Define `PaymentProvider` interface: `initiate_collection()` (pay-in),
  `initiate_payout()` (pay-out), `query_status()`, plus a normalised result/callback
  contract independent of Safaricom field names.
- **P1-02** Implement `MpesaAdapter` as the first provider; move all Daraja-specific
  code behind it (STK push, B2C, transaction-status query, security credential).
- **P1-03** Provider registry + per-operation routing (so op_type/currency/region can
  select a provider later).
- **P1-04** Normalise inbound callbacks into provider-agnostic events; the ledger
  posting path consumes the normalised form only.
- **P1-05** Sandbox vs live provider config separation.

## Acceptance criteria
- No Safaricom/Daraja field name appears outside `MpesaAdapter`.
- A stub `NullProvider`/`FakeProvider` lets money-path tests run with no network.
- Adding a hypothetical second provider requires zero changes to ledger/services.

## Status (2026-06-20, PR #16)
- ✅ **P1-01** `PaymentProvider` ABC + normalised dataclasses (`apps/payments/providers/__init__.py`).
- ✅ **P1-02** `MpesaProvider` wraps Daraja (STK/B2C + callback parsing); field names confined to it.
- ✅ **P1-03** `registry.get_provider()` + `use_provider()` override (per-op routing deferred until a 2nd rail exists).
- ✅ **P1-04** Outbound (STK/B2C) and inbound (STK/B2C callback views) both go through the provider; views consume normalised `CallbackEvent`s.
- ✅ **P1-05** `PAYMENT_PROVIDER` setting selects rail (auto-fake under DEBUG).
- 🔸 **Remaining:** `_legacy_b2c_result` fallback still parses Daraja (pre-FT welfare claims); `query_stk_status` not yet behind `query_status()`; rewrite the quarantined #14 M-Pesa tests against `FakeProvider`.

## Exit criteria
- [x] All rail I/O behind `PaymentProvider`; posting path is rail-agnostic (except the legacy fallback above).
- [x] Contract tests for the provider interface; fake provider used in CI (27 tests across providers + callbacks).
