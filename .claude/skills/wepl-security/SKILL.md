---
name: wepl-security
description: WEPL's two separate identities (customer phone+OTP vs back-office
  email+password), the staged JWT ladder, the STAGING_OTP_BYPASS production boot
  guard, KYC tier gating, ops RBAC + step-up, the verification case ledger, and
  the account-restriction chokepoint. Use when touching apps/users,
  apps/backoffice, apps/verification, apps/controls, authentication, permissions,
  settings, or any endpoint that needs to decide who may do what.
---

# WEPL security

## Two identities, never mixed

| | **Customer** | **Operator** |
|---|---|---|
| Model | `users.User` (`AUTH_USER_MODEL`) | `backoffice.StaffAccount` |
| Identifier | **`phone_number`** — there is no username | corporate **email + password** |
| Credential | OTP (+ a 6-digit hashed PIN) | admin-provisioned password, `must_change_password`, **no self-serve reset** |
| Token | SimpleJWT with a `stage` claim, `sid` session claim | own HS256 JWT, `type: "ops"`, 12 h TTL (`backoffice/auth.py`) |
| Authz | `core/policy.py`, `users/tiers.py`, `contributions/permissions.py` | capability map over `ops:*` Groups + `RequireCapability` |
| Audit | `apps/audit` | every action via `record_action()` |

`request.user` on an ops endpoint is a `StaffAccount`, **not** a `User`. Code
that duck-types on `request.user` behaves differently there. The console
frontend is a separate deployment and must never be co-hosted with the customer
web app.

## The staged JWT ladder (`apps/users/auth.py`)

```
otp_verified  phone proven, unfinished user  → may ONLY set a PIN
otp_recovery  phone proven, forgotten PIN    → may ONLY reset a PIN
active        full session                   → everything else
```

The project default permission must stay `IsActiveSession` so an intermediate
token can never reach a contribution, disbursement or M-Pesa endpoint. Only the
two PIN endpoints opt into the narrower `StageRequired`. An `active` token
carries a `sid` pointing at a `UserSession` (ADR-0010) so a login can be listed
and revoked; the `sid` survives refresh rotation.

## The OTP bypass guard — do not weaken it

`STAGING_OTP_BYPASS` accepts a fixed `000000` OTP for **any** phone number.
`config/settings/production.py` raises `ImproperlyConfigured` **at boot** if it
is set while `DEBUG=False`. This guard is intentional. Never relax it to a
warning, never make it conditional, never set the flag in production. In
production `SMS_BACKEND=console` routes real OTP codes to the logs.

`apps/users/tests.py::ProductionOtpBypassGuardTests` proves it by booting
`django.setup()` in a subprocess with production settings and asserting a
non-zero exit. That subprocess-boot pattern is the only way to test a
settings-module guard; copy it rather than importing the module.

## KYC tiers (ADR-0022) — know what is actually on

`apps/users/tiers.py::AccessPolicy`:
- **`require_tier1(user, msg)`** — unconditional. Used by the pre-existing money
  paths (`ContributionService.contribute`, `request_advance`). **Nobody
  bypasses it** — `is_staff`/`is_superuser` stopped bypassing on 2026-09-26.
- **`gate(user, msg)`** — flag-aware, for the newer Phase-B surfaces (community
  create/join, contribution create, chat). **It is a no-op while
  `ACCESS_TIER_ENFORCEMENT` is `False`, which is the default.** Do not read a
  `gate()` call as an active gate.

Tier 0 = phone verified, KYC not approved (discovery/read). Tier 1 = KYC
approved (full access). Tiers are derived from verification state; nothing extra
is stored.

## Identity is a ledger too (`apps/verification/`)

Every KYC journey is a `VerificationCase` whose immutable `CaseEvent` timeline is
the source of truth; `KYCProfile.status` is a **projection**. All decisions — ops
console, Django admin, automated provider outcomes — go through
`verification/service.py::decide`, the identity analogue of `post_journal()`: a
declared `_TRANSITIONS` table, a row lock, an appended event. `CaseDocument` rows
are versioned and pinned to their storage objects, so a re-submission adds a
version and never overwrites the evidence a prior decision was made against.

Never mutate `VerificationCase.state` or `KYCProfile.status` directly.

**The case ledger records the decision; it does not carry out the consequences**
(ADR-0033). `apps/verification` imports only `apps/core`. Anything a decision
should *do* elsewhere is registered into `verification/hooks.py` from the owning
app's `AppConfig.ready()`: `apps/controls` releases the held movement, issues the
pre-clearance and resolves the customer's `VerificationRequest`; `apps/users`
tells the applicant, through `users/notifications.py`. If a decision stops
reaching the applicant, the registration in `UsersConfig.ready()` is the first
thing to check — losing it is silent, and
`verification/tests.py::DecisionNotifiesApplicantTests` is what stands there.

Identity checks go through the `IdentityVerificationProvider` port
(`apps/users/identity/`, ADR-0023): `ManualProvider` (human review),
`FakeProvider` (tests), resolved via `registry.get_provider()` — the same shape
as the payments port. A real vendor or IPRS lookup drops in as another adapter
without touching the view.

## Ops RBAC (`apps/backoffice/`)

Capabilities are dotted strings (`ledger.adjust`, `verification.decide`,
`finops.reverse`, …) in a **code-defined** map over `ops:<role>` Django Groups
(`capabilities.py`). Enforcement is **server-side** via `RequireCapability`;
`/api/ops/me/` only tells the console what to render. Maker-checker is
object-level in the approvals flow — an `*.approve` capability means "may act as
a checker", never "may approve my own request". `RequireStepUp` requires a fresh
TOTP elevation token (`X-Ops-StepUp`) for sensitive actions and **explicitly does
not exempt superusers**. Every ops action writes an `AuditEvent`.

## The money chokepoint is also a security chokepoint

`controls/engine.py::enforce_controls` runs **inside `post_journal`**, so no money
path can bypass it. It checks account restrictions first
(`users/services.py::RestrictionService.blocks_money` — an ops freeze/payout
block/payin block is a hard DENY), then `LimitRule` velocity/amount rules.
Reversals and journals with no FT skip member-facing controls, by design.

## Other standing rules

- Raise Django exceptions (`PermissionDenied`, `ValidationError`) from services,
  not DRF ones; `core/exceptions.custom_exception_handler` maps them.
- `core/policy.py` fails **closed**: an unregistered action prefix raises
  `PolicyConfigurationError` rather than allowing.
- Throttles are fail-open by design (`core/throttling.py`) so a Redis outage
  degrades rate limiting instead of 500-ing the API. That is a deliberate
  availability trade, not an oversight.
- Third-party PII (`FinancialTransaction.counterparty_name`) is shown in full to
  operators and masked to members.

## Do not assume

- Do not assume `is_staff` means "an operator". It is a flag on a **customer**
  model that grants Django admin (read-only for money records since 2026-09-26)
  and `IsAdminUser` access to the ledger reporting endpoints. It no longer
  bypasses the KYC gate, the tenant pin or community policy.
- Do not assume a `gate()` call enforces anything today.
- Do not assume revoking a `UserSession` affects an ops token — the ops token has
  no revocation list, only a 12 h expiry plus the `StaffAccount.is_active` check.
- Do not assume the two token families are cryptographically separated: both are
  signed with the same `SECRET_KEY` and are distinguished by the `type` claim and
  by which authenticator decodes them.
- Do not assume `KYCProfile.status` is an input; it is a projection.

## Forbidden shortcuts

- Setting `STAGING_OTP_BYPASS` in production or moving the boot guard behind a
  flag.
- Granting `is_staff` to make something work.
- `KYCProfile.status = 'approved'; save()`.
- Enforcing a capability in the console frontend only.
- Adding a second place that mints staff tokens.
- Adding a break-glass exemption to `RequireStepUp`.
- Making throttles fail-closed "for security" without reading
  `core/throttling.py`'s rationale.

## Key tests

`apps/users/tests.py`, `tests_sessions.py`, `tests_tiers.py`;
`apps/verification/tests.py`; `apps/backoffice/tests.py`. CI holds
`users/sessions.py`, `users/token_views.py`, `core/policy.py`,
`audit/services.py` and `audit/models.py` to **≥90 %**.

**Gaps to know about** (as of `68e8cf6`, 2026-09-21): nothing tests that an
intermediate-stage (`otp_verified` / `otp_recovery`) token is refused by a money
endpoint — the ladder's whole point — and nothing tests that a customer JWT is
rejected by `/api/ops/*` or an ops token by a customer endpoint, which matters
precisely because both families are signed with the same `SECRET_KEY`.
