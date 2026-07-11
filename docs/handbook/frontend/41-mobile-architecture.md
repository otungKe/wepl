# Frontend / 41 — Mobile Architecture

> The member app — where most customers actually meet Wepl. Built on Expo / React
> Native, designed unapologetically for a **mid-range Android phone on a patchy
> network**, because that is the real device of the real user
> ([UX-7](../product/06-ux-and-design.md)).

Lives in `mobile/`. Stack: **Expo 54 · React Native 0.81 · React 19 ·
expo-router · React Navigation · axios · TypeScript**.

---

## Why Expo / React Native

- **One React mental model** shared with the [web frontends](40-frontend-architecture.md)
  — shared design tokens, shared primitives (the `Money` component), shared API
  types from the same OpenAPI schema.
- **Android-first reach.** The user base is on Android; RN + Expo delivers a native
  app there (and iOS) from one codebase.
- **OTA updates (EAS).** Expo's over-the-air updates (`eas.json`) let us ship fixes
  without waiting on store review — valuable for a money app where an honest-status
  fix should reach users fast.
- **Managed native modules** (camera for KYC capture, push via FCM) without dropping
  to bare native for the common cases.

## App structure

```
mobile/
├── app/          # expo-router routes (file-based navigation)
├── components/   # UI primitives + patterns (design system on-device)
├── api/          # typed API client (axios); the ONLY backend contract
├── hooks/        # data fetching, auth, device state
├── constants/    # design tokens, config
├── utils/        # formatting (money via the Money component), helpers
├── assets/       # images, fonts
├── app.json      # Expo config
└── eas.json      # build/OTA profiles
```

Navigation is **expo-router** (file-based) over React Navigation
(stack/tabs/drawer). The `api/` layer is the single boundary to the backend — every
screen goes through it, and it is generated/typed against the backend's OpenAPI
schema so the mobile client cannot drift from the API contract.

## Designed for the real device and network (UX-7)

This constraint drives concrete decisions, not just aspirations:

- **Offline-tolerant reads.** Balances, transactions, and community state are
  cached so the app is legible without a live connection; the app reconnects and
  refreshes gracefully. What's cached is always a *projection* of server truth,
  never a local authority.
- **Small payloads.** The API's pagination/filtering (inquiry-first transactions)
  keeps responses small and data-cheap — a real cost concern for the user.
- **Optimistic UI only where safe.** A draft, a read, a like may be optimistic; a
  **money confirmation never is** ([UX-3](../product/06-ux-and-design.md), **P-16**).
  The app waits for the backend's confirmed state before telling the user money
  moved.
- **Graceful degradation.** When the backend degrades honestly (a `503` on OTP under
  cache outage, commit #157), the app shows an honest "try again shortly," not a
  fake success or an opaque crash.

## Money moments on device

The mobile app is where [User Journey J3 (Contribute)](../product/05-user-journeys.md)
and J4 (Payout) are lived:

1. The app requests a **collection** via the API; the backend issues an M-Pesa STK
   push. The app shows a truthful *pending* state — money has not moved yet.
2. The member approves in the M-Pesa prompt (system-level).
3. The app reflects the **confirmed** result only after the backend has posted to
   the ledger on the rail callback. Never before.

The `Money` component renders every amount; the fixed status vocabulary
(*pending/success/failed/reversed/awaiting-vote*) renders every state, so a member
learns the language once and reads it everywhere.

## Auth on device

- **Phone + OTP** onboarding ([Identity J1](../product/05-user-journeys.md)); customer
  JWT stored securely on device; refresh handled transparently; revocation honored
  via the session registry ([ADR-0010](../../adr/0010-session-registry-and-token-revocation.md)).
- **KYC capture** on device (camera → document upload to object storage, feeding the
  identity ledger, versioned `CaseDocument`s, **P-11**). OCR assists server-side and
  degrades to manual review when unavailable ([ADR-0023](../../adr/0023-identity-verification-provider.md)).

## Notifications

Push via **FCM (Firebase)**, one channel of the multi-channel notification layer
([ADR-0015](../../adr/0015-multi-channel-notification-delivery.md)) driven by the
durable [outbox](../architecture/26-eventing-architecture.md). A push is a delivered
*effect* of a domain event, deduped on `event_id` — a member is never double-notified
even though delivery is at-least-once (**P-9**).

## Realtime

Group chat and live updates over the Channels WebSocket
([ADR-0012](../../adr/0012-chat-scaling.md)), authenticated with the JWT on connect,
tenant-scoped. Designed to reconnect cleanly on a flaky network rather than assume a
stable socket.

## Build and release

- **EAS build/update profiles** in `eas.json`; OTA updates for JS-only fixes, store
  builds for native changes.
- **The app ships in coordination with the API** (internal API versioning,
  [API Architecture](../architecture/23-api-architecture.md)) — breaking API changes
  are coordinated releases, and OTA lets a client-side fix follow quickly.

## What the mobile app must never do

- **Never treat cached/local state as money truth** — it is always a projection
  (**P-3**).
- **Never show optimistic success for unconfirmed money** (**P-16/UX-3**).
- **Never render raw money strings** — use the `Money` component (**P-4**).
- **Never assume a stable network** — design for reconnection and honest degradation
  (UX-7).

---

*Return to the [Frontend index](../README.md#5-frontend--mobile), or continue to
[Operations / Infrastructure](../operations/50-infrastructure.md).*
