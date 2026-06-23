# ADR-0010: Device/session registry & on-demand token revocation

- **Status:** Accepted (implemented in `apps/users/`)
- **Date:** 2026-06-23
- **Relates to:** Platform Hardening Review, finding #4 (auth hardening)

## Context

Auth is phone + OTP → staged JWT (ADR's `stage` claim), with SimpleJWT configured
for `ROTATE_REFRESH_TOKENS` + `BLACKLIST_AFTER_ROTATION`. Two gaps remained:

1. **No on-demand revocation.** There is no logout: a refresh token stays valid for
   its full 7-day life. The only blacklisting happens at account deletion. A user
   who loses a phone, or an operator responding to account takeover, cannot kill a
   live session. Access tokens (60-min life) are never checked against any
   revocation list at all — SimpleJWT only blacklists *refresh* tokens.
2. **No session visibility.** `OutstandingToken` rows exist but carry no device
   metadata and are not surfaced. Users can't see "where am I logged in" and can't
   revoke one device without nuking all of them.

## Decision

Add a first-class **session registry** and make revocation effective for both
token types, near-real-time.

- **`UserSession`** (one row per login) keyed by a `sid` UUID, carrying device
  label, user-agent, IP and `last_seen_at`, with a nullable `revoked_at`.
- **`sid` claim.** `issue_tokens(user, STAGE_ACTIVE, request=...)` creates a session
  and embeds its `sid` in the token. Because rotation and `TokenRefreshView` copy
  non-reserved claims, `sid` survives refresh — so one session spans the whole
  rotation chain. Intermediate (OTP-stage) tokens get **no** session.
- **Enforcement at both doors.** A `SessionJWTAuthentication` (the base of the
  existing `TenantJWTAuthentication`) rejects any token whose `sid` maps to a
  revoked/absent session and touches `last_seen_at`. A `SessionTokenRefreshView`
  applies the same check on the refresh path. Result: revoking a session kills its
  access tokens (within the auth check, immediately) **and** blocks refresh —
  independent of the blacklist.
- **Endpoints:** `logout` (blacklist the presented refresh + revoke the current
  session), `sessions` (list, current flagged), `sessions/<sid>/revoke`, and
  `sessions/revoke-others` ("log out everywhere else").

Revocation also best-effort blacklists the user's outstanding refresh tokens, but
correctness does not depend on it — the session check is the source of truth.

## Consequences

- **+** Real logout; immediate, per-device revocation; "log out everywhere".
- **+** Access tokens are now revocable (the long-standing SimpleJWT blind spot).
- **+** Users/operators get session visibility for incident response.
- **−** One indexed `UserSession` lookup per authenticated request; `last_seen_at`
  writes are throttled (≤ once/60s per session) to keep it cheap.
- **−** Tokens minted before this change have no `sid`; they are allowed through
  (can't be session-revoked) until they expire. Acceptable transitional state.

## Alternatives considered

- **Blacklist-only (no registry).** Rejected: doesn't cover access tokens, gives no
  device visibility, and `OutstandingToken` can't be mapped to a logical session
  across rotation.
- **Short access-token TTL instead of revocation.** Rejected as insufficient alone;
  60-min exposure on a stolen token is too long for a finance app, and it still
  offers no "see/kill my sessions".
- **Server-side sessions (DB/Redis) replacing JWT.** Rejected: far larger blast
  radius; the `sid`-on-JWT approach keeps the stateless fast path and adds state
  only for revocation.
