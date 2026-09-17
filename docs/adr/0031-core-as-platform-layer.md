# ADR-0031: Core is a platform layer — the registry contract

- **Status:** Accepted (2026-09-17)
- **Date:** 2026-09-17
- **Deciders:** Architecture review — Core boundary
- **Relates to:** generalizes the authorization registry (ADR-0009) into a Core-wide
  contract; completes the deferred "presentation off the bus" move (ADR-0029 "Fork
  B") and stages the eventing split onto ADR-0029 Stage 2; touches the KYC tier
  exception (ADR-0022) and the controls chokepoint exceptions (ADR-0007).

## Context

`apps/core` is meant to be the **platform layer** — the technical mechanisms every
app relies on — not a dumping ground for business logic. A module-by-module audit
against a single test —

> **A Core module is legitimate platform iff it is a mechanism business plugs into:
> it names no specific business concept and imports no business app.**

— shows Core is *mostly* already there, with a clear exemplar of the right pattern
and exactly two leaks.

**Clean platform** (mechanisms, no business knowledge): `ids` (uuid7),
`encryption`, `pagination`, `throttling`, `middleware`, `observability`, `health`,
`dispatch`, `deploy_checks`, `models` (`OutboxEvent`/`WorkerHeartbeat`), `tasks`
(the relay).

**The exemplar — `apps/core/policy.py` (ADR-0009).** Core defines the seam
(`can`/`require`, and `@policy("<prefix>")` to register a resolver, `policy.py:60-78`);
business apps register their resolvers *from their own* `AppConfig.ready()`; Core
knows only opaque string prefixes and never imports a business app. This is exactly
the shape the rest of Core should hold.

**Leak 1 — `apps/core/events.py`.** `emit()` (`:35-39`) hardcodes notification
*presentation* (`user_id`, `title`, `message`) **and** specific business FK hints
(`community_id`, `conversation_id`, `contribution_id`, `join_request_id`). A
platform event bus that knows what a notification looks like and that "contribution"
exists. This is the same smell ADR-0029 named and deferred as "Fork B."

**Leak 2 — `apps/core/exceptions.py`.** The platform DRF error-mapper has been made
to know *business* exceptions:

- `KYCRequired` (`:41-60`) — a users/KYC concept, hardcoding the tier envelope and
  `/kyc/start` (ADR-0022).
- `LimitExceeded` / `ControlHeld` (`:97-120`) — controls-chokepoint concepts
  (ADR-0007), and the handler **imports `apps.controls.review` at `:193`** to record
  the blocked movement.

That import is the **only** `from apps.<business>` anywhere in `apps/core` — the one
hard structural inversion: a platform module reaching *up* into a business app.
Every other business-concept mention in Core (`dispatch`, `deploy_checks`,
`pagination`) is comment-level, not structural.

Beyond the two leaks there is a deeper packaging question: Core mixes *technical
platform* (uuid7, pagination) with *domain-event infrastructure* (the outbox model +
relay), and ADR-0029 is about to grow that outbox into a first-class subsystem
(delivery rows, execution lanes, a subscription registry). Bundling a growing
event-log subsystem beside `pagination` understates it.

## Decision

**Core is the technical platform layer, held to one rule, with the two leaks closed
and the event bus promoted to its own context on a staged schedule.**

### 1. The Core contract (generalize `policy.py`)

> Core imports no business app and names no specific domain concept. Business plugs
> into Core-defined seams by *registering* from its own `AppConfig.ready()`; Core
> holds only the mechanism and opaque keys.

`policy.py` already embodies this; it becomes the stated contract for every Core
seam, not an isolated pattern.

### 2. Fix Leak 2 — exception mapping becomes a registry

Core keeps the *mapping mechanism* and the genuinely cross-cutting **platform
primitives**, which have no single business owner and map to generic HTTP semantics:

- `TransitionError` — state-machine optimistic-lock conflict (raised by ledger,
  payments, verification alike) → 409,
- `RateLimitError` → 429,
- `ServiceUnavailable` → 503.

The *business* exceptions move to their owning app and register their own
`(exception → status + renderer)` mapping from `AppConfig.ready()`:

- `KYCRequired` → `apps/users` (owns the tier envelope and `/kyc/start`, ADR-0022),
- `LimitExceeded` / `ControlHeld` → `apps/controls` (ADR-0007), and the
  `record_blocked_movement` side-effect rides with the controls registration.

`apps/core/exceptions.py:193`'s `import apps.controls.review` is **deleted** — the
inversion is gone; Core no longer names KYC or controls.

### 3. Fix Leak 1 — presentation off the bus (= ADR-0029 "Fork B")

`emit()` stops carrying notification presentation and business FK hints; the bus
carries `(event_type, envelope, body)` and knows nothing about notifications or
contributions. This is not new scope — it is ADR-0029's deferred Fork B, hereby
confirmed as *the* Core fix and owned by this ADR's boundary work. Notification
title/message/recipient becomes a notification *policy* (in `apps/notifications`)
that maps a domain fact to a notification, registered the `policy.py` way.

### 4. Promote the event bus to its own `eventing` context — staged

The outbox model + relay move out of `apps/core` into a dedicated infrastructure
context (`apps/eventing`), leaving Core as pure technical platform. This is
**staged onto ADR-0029 Stage 2**, not done now: Stage 2 already adds tables
(`OutboxDelivery`) and the subscription registry, so it is the natural,
no-extra-cost moment to relocate `OutboxEvent`/relay. Doing it now would be a
standalone table-move migration for no immediate benefit — the same staging
discipline used across ADR-0028/0029/0030.

## Consequences

- **+** Core is provably platform: no business import (the `:193` inversion gone),
  no domain naming; the one-line contract makes future violations obvious in review.
- **+** The two leaks close via the *existing* good pattern (`policy.py`), so the fix
  is a generalization, not a new mechanism.
- **+** Business error semantics live with the business that owns them; adding a new
  business exception no longer edits a Core file.
- **+** The event bus becomes a first-class context sized to what ADR-0029 makes it,
  and the relocation costs nothing extra by riding Stage 2's migration.
- **+** Leak 1's fix is unified with ADR-0029, so "Fork B" has one owner instead of
  floating between two ADRs.
- **−** The exception-registry indirection is slightly less greppable than one
  central handler (mitigated: registrations are in each app's `AppConfig.ready()`,
  the same place policies already live).
- **−** Moving `OutboxEvent`/`WorkerHeartbeat` to `apps/eventing` is a real (if
  deferred) migration; until Stage 2 lands, the event bus still sits in Core.
- **−** ~4 call sites raising the moved exceptions must import them from their new
  home; the generic primitives (`TransitionError` et al.) are unaffected.

## Alternatives considered

- **Keep the central exception handler; just delete the `apps.controls` import.**
  Rejected — it removes the worst inversion but leaves Core still *naming* KYC and
  controls exceptions; the registry puts ownership where it belongs and matches
  `policy.py`.
- **Move `TransitionError`/`RateLimitError`/`ServiceUnavailable` out too.** Rejected
  — these are cross-cutting *mechanism* exceptions with no single business owner
  (state machines and infra live in many apps); they are genuinely platform.
- **Split `eventing` out of Core now.** Rejected as premature — a standalone
  table-move migration for no immediate gain; staged onto ADR-0029 Stage 2 where the
  migration happens anyway.
- **Leave the event bus in Core permanently.** Rejected — ADR-0029 grows it into a
  subsystem with its own model, lanes and registry; keeping it beside `pagination`
  understates a first-class infrastructure context.
- **Treat Leak 1 as separate from the Core boundary.** Rejected — it *is* the Core
  boundary at the event bus; unifying it with ADR-0029's Fork B avoids two ADRs
  owning one change.
