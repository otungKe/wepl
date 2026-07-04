# ADR-0022: Two-tier access model (KYC-gated full access)

- **Status:** Accepted. Phase A shipped (tier model + centralized gate + structured error + consolidation). **Phase B shipped the backend enforcement** — the flag-aware `gate()` wired onto community create/join, contribution create, and chat — **behind `ACCESS_TIER_ENFORCEMENT` (default off)**. Follow-ups now landed: the money front-door (M-Pesa STK push) is gated **unconditionally** via `require_tier1`; the remaining member write surfaces (join requests, disbursement/amendment votes + requests/proposals, welfare claim submission, standing orders) carry the flag-aware `gate()`; and the web frontend mirrors the mobile tier model (unverified nav + route guard). See "Phase B" below.
- **Date:** 2026-07-03
- **Relates to:** Onboarding & access-control spec; builds on the authorization policy layer (ADR-0009) and the API error conventions (ADR-0021).

## Context

Onboarding should minimise signup friction while keeping money behind identity
verification. The pieces already existed but were **ad-hoc**: KYC status lives on
`KYCProfile` (`pending`/`approved`/`rejected`), phone verification on
`User.is_phone_verified` (set by the OTP flow), and two service methods
(`ContributionService.contribute`, `EmergencyAdvanceService.request_advance`)
hand-checked `user.kyc.status != 'approved'` and raised a **400 ValidationError**
with bespoke wording. There was no shared notion of an access "tier", and the
error the client saw was inconsistent with a "verify to unlock" experience.

## Decision

### Two derived tiers (nothing extra stored)
Access is a **function of verification state**, computed on `User`:

| Tier | Condition | Access |
|---|---|---|
| **Tier 0** | phone verified, KYC not approved | discovery / public reads, edit own profile, start KYC |
| **Tier 1** | phone verified **and** KYC `approved` | full platform |

`pending`/`rejected` KYC do **not** grant Tier 1. Properties on `User`:
`kyc_status` (safe accessor → `not_submitted` when absent), `is_tier1`, `is_tier0`,
`has_full_access()`. No columns added — a migration would be redundant state that
could drift from the source of truth.

> Note on phone verification: in production you cannot obtain approved KYC without
> an authenticated (OTP-verified) session, so `phone_verified ∧ kyc_approved` is
> equivalent to `kyc_approved` for real users. Requiring both is defensive and
> matches the spec; only test fixtures that skip OTP must set `is_phone_verified`.

### One centralized gate
`apps/users/tiers.py` exposes `AccessPolicy` — the tier counterpart to the
resource-scoped `apps/core/policy.py`:

- `AccessPolicy.is_tier1(user)` / `is_tier0(user)` / `has_full_access(user)` — pure predicates.
- `AccessPolicy.require_tier1(user, message=None)` — raises `KYCRequired` unless the
  user is Tier 1. **Staff/superusers bypass** (platform operators), mirroring the
  policy layer.

`RequiresTier1` (`apps/users/permissions.py`) is the DRF view-layer counterpart,
composed after `IsActiveSession`. Both raise rather than returning a bare `False`
so the client always gets the structured envelope.

### Structured `KYC_REQUIRED` 403
`KYCRequired` (`apps/core/exceptions.py`) subclasses Django's `PermissionDenied`
so it can be raised from services, Celery and WS consumers. The exception handler
renders it — **before** DRF's default handler, which would otherwise flatten this
`PermissionDenied` subclass into a generic `{"detail": …}` 403 — as:

```json
{ "code": "KYC_REQUIRED",
  "message": "Complete identity verification to unlock all platform features.",
  "next_step": "/kyc/start" }
```

### Consolidation (Phase A, no access-behaviour change)
The two hand-rolled `kyc.status != 'approved'` checks now call
`AccessPolicy.require_tier1(...)`. The **set of who-can-do-what is unchanged** — the
same unverified users are blocked from the same actions; only the error contract
improves (was a 400 `ValidationError`, now the consistent 403 `KYC_REQUIRED`).

## Consequences

- **Positive:** a single, testable definition of "full access"; consistent
  structured error the mobile/web clients can branch on (mobile already has
  `useKYCGate`); the ad-hoc checks are gone. Extending to more tiers later is a
  new `is_tierN`/`require_tierN` without touching call sites.
- **Behaviour delta:** the two money-path errors change from **400 → 403** with a
  new body shape. Same access outcome; clients parsing that specific error must
  read `code`.
- **Deferred to Phase B (needs product decisions):**
  1. **"Tier 0 = email + phone verified"** — base signup is phone-OTP only; email
     verification currently lives *inside* KYC. Phase A treats **phone-verified** as
     Tier 0. Whether to add an email step to signup is an open product call.
  2. **Feature vocabulary** — the spec lists campaigns / harambees / wallet /
     follow / react-comment, which **don't exist** as apps. The real Tier-1 surfaces
     are communities, contributions (savings/ROSCA/welfare/shares/advances),
     conversations (chat), invitations, payments/ledger.
  3. **Backward compatibility** — today an active user can join communities and
     chat without KYC. Hard-gating those is a breaking change for existing
     unverified users; it needs a grandfathering / feature-flag / grace-period
     cutover before `RequiresTier1` is wired onto those endpoints.

## Phase B — enforcement, safe by construction

The three open decisions were resolved with the lowest-risk defaults:

1. **Tier 0 = phone-verified** (email stays a KYC concern; no signup rebuild).
2. **Vocabulary → real apps.** The gated surfaces are the ones that exist:
   community create/join, contribution (pool) create, chat (conversation + message).
   Remaining member writes now carry the same flag-aware gate: community join
   requests, disbursement requests + votes, amendment proposals + votes, welfare
   claim submission, and standing-order setup. Member money-in (welfare/shares
   contributions) flows through the STK-push front-door, which is gated
   **unconditionally** (`require_tier1`) rather than flag-aware, since it moves money.
3. **Backward compatibility = a feature flag, default off.**
   `ACCESS_TIER_ENFORCEMENT` (settings) is the master switch. `AccessPolicy.gate()`
   is a **no-op while it is off**, so the gate is wired onto currently-open
   endpoints but stays inert until the switch is flipped — existing
   active-but-unverified users are unaffected. Flip to `true` in production after a
   KYC push. (The pre-existing money-path checks via `require_tier1` always enforce,
   flag or not.)

Two gates, by intent:
- `AccessPolicy.require_tier1(user)` — **unconditional** (contribute / request_advance; pre-existing).
- `AccessPolicy.gate(user)` — **flag-aware** (all new Phase-B surfaces); `RequiresTier1` uses it.

Rollout: enable in staging → verify Tier-0 gets `KYC_REQUIRED` on the gated
surfaces and Tier-1 is unaffected → announce/KYC-push → enable in production. Roll
back instantly by flipping the flag off. A future refinement can grandfather
pre-cutoff users instead of a hard global switch.

`render.yaml` provisions a dedicated staging stack for exactly this — `wepl-api-staging`
+ `wepl-web-staging` with their own `wepl-db-staging`/`wepl-redis-staging`, identical
to production except `ACCESS_TIER_ENFORCEMENT="true"`. Validate the Tier-0 experience
there first, then set the same flag on `wepl-api`.

**Enforcement is now enabled in production** (`ACCESS_TIER_ENFORCEMENT="true"` on
`wepl-api`) — unverified users are gated on the flag-aware surfaces. Roll back
instantly by setting it back to `"false"`.

## Extension points
- New tier: add the derived property + `AccessPolicy.require_tierN`.
- New gated endpoint (Phase B): `permission_classes = [IsActiveSession, RequiresTier1]`,
  or `AccessPolicy.require_tier1(user)` at the service boundary.
- Per-action nuance: give `AccessPolicy.can_*` real logic without changing call sites.
