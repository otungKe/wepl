# Frontend / 40 — Frontend Architecture

> The customer web app and the operations console — two React/Next.js applications
> with deliberately different jobs, sharing conventions but not a codebase or a
> deployment. The design language and UX principles they implement live in
> [UX Philosophy & Design System](../product/06-ux-and-design.md); this chapter is
> about *structure*.

---

## Two web applications, one platform

| App | Directory | Users | Deployment |
|-----|-----------|-------|------------|
| **Member web** | `web/` (Next.js) | customers | `wepl-web` (Render, Node) |
| **Ops console** | `backoffice/` (Next.js) | operators | separate deployment (**P-12**) |

They are **separate Next.js apps** on purpose. The [Identity Architecture](../domain/14-identity-architecture.md)
demands that customer and operator surfaces never share an identity, a token, or a
deployment (**P-12**); making them separate applications makes that separation
structural rather than a matter of careful routing. A bug in the member app cannot
expose ops functionality, because the ops code is not in the member app's bundle at
all.

## Shared stack, shared conventions

Both apps are **Next.js + React + TypeScript + Tailwind**. Sharing the stack means:

- One mental model for engineers moving between them.
- A **shared design system** — tokens and truly-universal primitives (the `Money`
  component, `StatusBadge`, `Button`, `Field`) can be shared, while surface-specific
  patterns are not force-fit ([Design System](../product/06-ux-and-design.md)).
- TypeScript everywhere, so the API contract is typed. The backend's
  **drf-spectacular OpenAPI schema** ([API Architecture](../architecture/23-api-architecture.md))
  is the source for generated, typed API clients — the frontend's types derive from
  the same schema the backend generates, so they cannot silently drift.

## Architectural conventions

### The API is the only backend contract
Frontends talk to the backend exclusively through the documented REST/JSON API
(+ WebSocket for realtime). No frontend reaches around the API into the database or
assumes internal model shapes. The uniform error envelope and honest status codes
([API Architecture](../architecture/23-api-architecture.md)) let the frontends handle
errors generically — a `503` is a "degraded, retry" state, a `409` is a conflict, a
`402/403` distinguishes payment from permission.

### Money is never a raw number in the UI
Every monetary value renders through the **`Money`/`Amount` component**, the UI
analogue of the `Money` value object (**P-4**). Currency, precision, and sign are
formatted in one place. Hand-formatting a currency string is a rejected anti-pattern
([UX Design System](../product/06-ux-and-design.md)).

### Honest money states
The UI reflects true backend state — *pending / success / failed / reversed /
awaiting-vote* — from the fixed status vocabulary, and **never shows optimistic
success for unconfirmed money** ([UX-3](../product/06-ux-and-design.md), **P-16**).
Optimistic UI is used only where it is *safe* (a like, a draft), never for a money
confirmation.

### Auth and session
- **Member web:** customer JWT (SimpleJWT), obtained via phone+OTP, with refresh and
  the session-registry-backed revocation ([ADR-0010](../../adr/0010-session-registry-and-token-revocation.md)).
- **Ops console:** staff JWT (`type:"ops"`), obtained via email+password, gated by
  `RequireCapability` server-side; the UI reflects the operator's capabilities but
  the *enforcement* is always on the server (the UI never gates authority itself).
- Tokens are handled per each app's security posture; the two never share storage.

### Realtime
Live updates and chat use the Channels WebSocket surface
([ADR-0012](../../adr/0012-chat-scaling.md)), authenticated with the same JWT on
connect and tenant-scoped like REST. Realtime is a transport for the same domain, not
a second authority model.

## The ops console is a different design language

The member app optimizes for *calm and legibility*; the ops console optimizes for
*density, precision, and speed* for an expert operator resolving exceptions
([UX §Two products, two moods](../product/06-ux-and-design.md)). They intentionally
do **not** share a look — forcing one design language across both degrades both. The
console surfaces the ops workflows: reconciliation/suspense
([Payments](../architecture/27-payments-architecture.md)), KYC review
([Identity](../domain/14-identity-architecture.md)), the transactions registry
(inquiry-first search, commits #148–#149), and every action it offers writes an
`AuditEvent` server-side (**P-14**).

## Rendering strategy (Next.js)

- **Member web** favours fast first paint and good behaviour on mid-range devices
  and patchy networks (the same constraint the [mobile app](41-mobile-architecture.md)
  designs for). Server rendering is used where it improves perceived performance;
  money-sensitive views always reflect *confirmed* server state.
- **Ops console** is an authenticated internal tool; it optimizes for
  data-density and interaction speed over first-paint marketing performance.

## What the frontends must never do

- **Never gate authority in the UI alone** — the server is the enforcement
  ([Governance](../domain/13-governance-architecture.md), **P-13**).
- **Never render money as a raw string** (**P-4**).
- **Never show optimistic success for unconfirmed money** (**P-16**).
- **Never mix member and ops surfaces** into one app (**P-12**).
- **Never assume internal API shapes** — consume the versioned, schema-typed contract.

---

*Continue to [Mobile Architecture](41-mobile-architecture.md).*
