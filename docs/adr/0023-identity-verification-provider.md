# ADR-0023: Identity-verification provider port/adapter

- **Status:** Accepted
- **Date:** 2026-07-05
- **Relates to:** Two-tier access model (ADR-0022) — this is the check that moves a
  user from Tier 0 → Tier 1. Mirrors the payment provider port/adapter (ADR-0005)
  and notifies via the transactional outbox (ADR-0006).

## Context

KYC in WEPL is manual: an applicant types their identity (given names, surname,
national ID number, date of birth) and uploads an ID scan + selfie. Approval was
a **human decision** in the Django admin, except under `DEBUG`, where confirming
the verification email auto-approved so developers get instant access.

That auto-approve/where-a-vendor-would-go logic was an inline `if DEBUG:` block in
`KYCEmailVerifyView` with a prose TODO ("call IPRS, call a selfie-liveness API").
Wiring a real automated checker — an identity-verification vendor, or a direct
lookup against Kenya's population registry (IPRS) — would have meant editing that
view and threading vendor field names through the KYC flow. There was **no seam**
for a third-party checker to drop into, and no record of what checked a submission
or why it passed/failed.

## Decision

Introduce an **`IdentityVerificationProvider` port** (`apps/users/identity/`),
modelled on the `PaymentProvider` port (ADR-0005):

- **Normalised types.** `IdentitySubject` (the claimed identity, assembled from a
  `KYCProfile` but decoupled from the ORM — image fields are storage paths, not
  handles) in, `IdentityCheckResult` out. The result's `state` is one of
  `verified` / `rejected` / `manual_review` / `pending`; adapters never leak
  vendor field names upward.
- **Adapters.** `ManualProvider` (default — routes every submission to human
  review; today's production behaviour) and `FakeProvider` (deterministic, no
  network; verifies by default, configurable to reject / review for tests).
- **Registry.** `get_provider()` selects on `settings.IDENTITY_PROVIDER`; empty →
  `fake` under `DEBUG`, else `manual`. This **preserves historical behaviour
  exactly** (dev auto-verifies, prod waits for a reviewer). `use_provider()` lets
  tests override with no network.
- **One call site.** `KYCEmailVerifyView` calls `_run_identity_check(kyc)` after
  the email is confirmed. It runs the active provider, **records the outcome** on
  the KYC row (`verification_provider`, `verification_ref`, `verification_state`,
  `verification_detail`, `verification_checked_at`), derives the KYC `status`
  (`verified`→approved, `rejected`→rejected, `manual_review`/`pending`→pending),
  and notifies the applicant on a terminal decision via the existing
  `_notify_kyc_decision` (durable outbox → `kyc_approved` / `kyc_rejected`).
- **Fail-safe.** A provider exception never loses the submission — it falls back
  to `status='pending'` (human review).

An asynchronous vendor (result arrives via webhook) returns `pending` with a
`provider_ref`; the port already declares `parse_callback()` for the webhook to
resolve later. No webhook endpoint is wired yet — no vendor is selected.

## Consequences

- **A real checker drops in as one adapter** (e.g. `iprs.py`, or a vendor adapter)
  plus a settings flag — `KYCEmailVerifyView` and the KYC flow are untouched.
- **Auditability:** every submission now records which checker ran and what it
  returned, for both manual and automated paths.
- The `DEBUG`-only branch and the cross-app `contributions.services._notify`
  import are gone; the KYC-approved/rejected notification now goes through the
  single durable path used by the admin actions.
- **Out of scope (follow-ups):** ID-scan *detection* + OCR field extraction
  (reading a Kenyan ID to pre-fill/cross-check typed values); the async webhook
  endpoint; and choosing an actual vendor / IPRS integration. These are deferred
  pending a capture-and-OCR decision.

## Alternatives considered

- **Keep the inline `if DEBUG:` and add the vendor call there.** Rejected — no
  seam, no test isolation, vendor field names leak into the view, no audit trail.
- **A Celery task per vendor.** Rejected for now — the port is transport-agnostic;
  an adapter that needs async work can enqueue internally. Adding a task layer
  before a vendor exists is speculative.
- **Store the vendor's raw response as the source of truth.** Rejected — the KYC
  `status` remains the authority (consumed everywhere via ADR-0022 tiers); the raw
  vendor payload is kept in `verification_detail` for audit only.
