# Architecture / 23 — API Architecture

> The conventions every Wepl API obeys, how the surface is versioned and
> documented, and the shape of the eventual public **BaaS** API. Consistency here
> is a feature: an API that behaves the same way everywhere is one a client can
> trust and one an engineer can extend without re-reading the rules.

Grounded in [ADR-0021](../../adr/0021-api-conventions.md); built on Django REST
Framework with OpenAPI via drf-spectacular.

---

## The API surfaces

Wepl exposes three logically distinct APIs from one backend:

1. **Customer API** — the member app + member web. Customer JWT auth. `/api/...`.
2. **Ops API** — the back-office console. Staff JWT (`type:"ops"`),
   `RequireCapability`. `/api/ops/...`. A *different audience, authority, and
   audit posture* ([Identity Architecture](../domain/14-identity-architecture.md)).
3. **Public / BaaS API** — the future external surface (Phase 7): API-key auth,
   tenant-scoped, webhooks-out, sandbox. Not yet built, but the conventions below
   are chosen so it is an *extension*, not a reinvention.

Keeping these as distinct, clearly-prefixed surfaces (rather than one API with
role flags) is the API-layer expression of **P-12**: audiences with different
authority get different doors.

## Conventions (ADR-0021)

These apply to every endpoint. They exist so that a client written against one part
of the API generalises to the rest.

- **REST over HTTP/JSON**, resource-oriented, predictable nouns and verbs.
- **JWT bearer auth**; the token *kind* (customer vs `ops`) selects the plane.
- **Consistent error envelope.** Errors flow through a single custom DRF exception
  handler that returns a uniform shape (code, message, detail) with correct HTTP
  status — never a bare stack trace, never a 200 wrapping a failure. Clients can
  handle errors generically.
- **Honest status codes.** `503` when a dependency is down (**P-16**), `409` on
  idempotency/conflict, `402/403` distinguished for payment vs permission — the
  status code tells the truth about what happened.
- **Idempotency is first-class.** Money-moving requests carry an idempotency key
  that maps to the ledger's `idempotency_key` (**P-2**), so a retried request is
  safe by construction, end to end from client to journal.
- **Pagination, filtering, and consistent list envelopes** for collection
  endpoints (e.g. the transactions registry: inquiry-first — you *search*, you do
  not blindly list — with date/amount/account/fund filters, commits #148–#149).
- **Money is always structured**, never a bare number: amount + currency, mirroring
  the `Money` value object (**P-4**) so a client can never misread a value's
  currency or precision.
- **Throttling on sensitive paths** (auth, money), which **fails open on a cache
  outage** rather than locking everyone out (commit #155) — honest degradation at
  the edge.

## Schema and documentation

The API is **schema-first-documented** via drf-spectacular: the OpenAPI schema is
generated from the code, so the docs cannot drift from the implementation. The
schema is the machine-readable contract; for the public API it becomes the source
of the client SDKs and the sandbox. "The schema is generated, not hand-written" is
the API-layer version of "the report is the ledger, summed" — one source of truth,
projected.

## Versioning

- **Internal (customer/ops) APIs** evolve with the app; the mobile/web clients ship
  in lockstep, so breaking changes are coordinated releases rather than a
  version-negotiation problem.
- **The public/BaaS API is versioned explicitly** (path or header) because external
  clients upgrade on *their* schedule, not ours. A public API is a promise; the
  versioning policy is how we keep it without freezing the platform. Deprecation is
  announced, dual-supported for a window, then retired — a discipline that only
  begins when Phase 7 does.

## Realtime surface

Beyond REST, Wepl exposes **WebSocket** endpoints via Channels for chat
([ADR-0012](../../adr/0012-chat-scaling.md)) and live updates. These carry the same
auth model (JWT on connect) and the same tenant scoping as REST; they are a
*transport* for the same domain, not a separate authority model.

## The BaaS API (Phase 7) — designed-for, not built-yet

The public API is the [Vision](../product/01-vision.md)'s endgame, and the
conventions above are chosen to make it a natural extension:

- **Auth:** API keys per tenant (not user JWTs), scoped to capabilities.
- **Isolation:** every call is tenant-scoped (**P-19**, [ADR-0008](../../adr/0008-multi-tenancy.md));
  a tenant can only ever see its own ledger.
- **Webhooks-out:** the same [outbox](26-eventing-architecture.md) that drives
  internal notifications drives external webhooks — at-least-once, signed, retried.
  The durable-eventing investment (**P-9**) *is* the webhook infrastructure; Phase 7
  largely exposes what Phase 2 already built.
- **Sandbox:** a tenant environment backed by the `FakeProvider` rails and
  `FakeProvider` identity, so integrators build against realistic behaviour without
  touching real money.
- **Money still moves only through `post_journal()`** on the tenant's ledger.
  Nothing about "external" relaxes **P-2**; the public API is just another caller of
  the one door.

That last point is the whole thesis: the public API is safe to expose *because* the
core it exposes has exactly one money door with all the invariants attached. A
platform with scattered money paths could not be safely opened to third parties.

## What the API layer must never do

- **Never move money outside `post_journal()`** to "make an endpoint simpler."
- **Never leak provider vocabulary** (Daraja field names) into responses (**P-18**);
  clients see normalized results.
- **Never return an optimistic success** for a money action that has not been
  confirmed on the rail and posted ([UX-3](../product/06-ux-and-design.md), **P-16**).
- **Never mix the customer and ops planes** into one authority-flagged endpoint
  (**P-12**).

---

*Continue to [Data Architecture](24-data-architecture.md) and
[Security Architecture](25-security-architecture.md).*
