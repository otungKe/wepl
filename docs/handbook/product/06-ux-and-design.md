# Product / 06 — UX Philosophy & Design System

> How Wepl should *feel*, and the system that keeps it feeling that way across the
> mobile app, the customer web app, and (in its own idiom) the ops console. UX in a
> financial product is not decoration; it is where trust is either earned or lost
> in the seconds around a money moment.

---

## The UX thesis

**Wepl's UX job is to make collective money legible and money moments calm.** The
user is often financially anxious, on a mid-range Android phone, over patchy data,
managing money that is not only theirs but their group's. Everything below follows
from taking that user seriously.

## UX principles

### UX-1 — Legibility over density
At a glance a member must know: *what do I owe, what have I paid, what does the pool
hold, what happens next.* If they have to interpret a screen to answer those, the
screen has failed. Prefer plain numbers with clear labels over dashboards that
impress but require decoding.

### UX-2 — The money moment is sacred
Paying in, receiving a payout, a transaction failing — these are the highest-anxiety
moments. In them the product must be maximally clear and honest: show real status,
never an optimistic guess; show the fee as a line item (it *is* a ledger line, and
[Philosophy §1/§7](02-philosophy.md) demands we not hide it); confirm with the
actual result, not a hopeful animation.

### UX-3 — Honest status, always
State is shown truthfully: *pending*, *failed*, *reversed*, *awaiting vote*. A
pending payment never masquerades as complete. This mirrors **P-16** at the UI
layer — the interface is as honest about failure as the backend is.

### UX-4 — Trust is shown, not asserted
Because trust is the product, the UI makes provability *visible*: every transaction
has a reference the member can cite, a counterparty, and a trail. "You can always
see where the money went" is a feature we surface, not a backend detail we hide.

### UX-5 — Governance is legible
When an action needs the group's consent, the UI makes the *why*, the *threshold*,
and the *current tally* obvious. Collective decisions should feel like collective
decisions, not opaque delays.

### UX-6 — The software disappears
The best session is a short one that ends in confidence. We optimise for the user
trusting the money is right and closing the app — not for time-in-app. Engagement
metrics that reward anxiety are the wrong metrics for a money product.

### UX-7 — Designed for the real device and the real network
Mid-range Android, small screens, intermittent connectivity, data cost sensitivity.
Offline-tolerant reads, optimistic UI only where it is *safe* (never for money
confirmation), small payloads, and graceful reconnection are defaults, not
enhancements. See [Mobile Architecture](../frontend/41-mobile-architecture.md).

### UX-8 — Accessible and inclusive by default
High contrast, scalable type, clear tap targets, and language that assumes low
financial jargon literacy. The product serves people across a wide range of
financial confidence; it must never make anyone feel they lack the vocabulary to
manage their own money.

---

## Two products, two moods

| Surface | Users | Mood | Priority |
|---------|-------|------|----------|
| Member app (mobile + web) | Members, admins | Calm, reassuring, plain | Legibility, honest money moments |
| Ops console | Operators | Dense, precise, auditable | Information density, traceability, speed |

These are intentionally *different* design languages. The member app optimises for
reassurance and low cognitive load; the ops console optimises for an expert
operator resolving exceptions quickly with full context. They are separate
applications and separate deployments (**P-12**) and should not be forced to share
a look at the cost of either's job.

---

## The design system

A design system exists so the product reads as *one voice* and so engineers make
consistent choices without re-deciding them each time. Its purpose is consistency
and speed, not novelty.

### Structure (tokens → primitives → patterns)
1. **Design tokens** — the single source of truth for colour, type scale, spacing,
   radius, elevation, motion. Tokens are named semantically (`color.text.primary`,
   `color.status.pending`) not literally (`gray-700`), so the same token maps
   correctly across light/dark and across member vs ops surfaces.
2. **Primitives** — the irreducible components (Button, Field, Money, Amount,
   StatusBadge, Avatar, Sheet). A **`Money` component** is a first-class primitive:
   money is *never* rendered as a raw number; it always goes through a component
   that formats currency, precision, and sign consistently — the UI analogue of the
   `Money` value object (**P-4**).
3. **Patterns** — composed flows (PaymentSheet, ContributionCard, VoteBanner,
   TransactionRow, Confirmation). Patterns encode the UX principles so they are
   obeyed by construction.

### Design-system principles
- **Status has a fixed vocabulary and a fixed palette.** *pending / success /
  failed / reversed / awaiting-vote* each have one colour and one label,
  everywhere. A member learns the language once.
- **Money is always a `Money`/`Amount` component**, never a hand-formatted string.
- **Semantic tokens, theme-aware.** Light and dark are both first-class; components
  read tokens, never raw values, so a theme is a token swap.
- **Accessible by construction.** Contrast and tap-target minimums are enforced at
  the primitive level, not left to each screen.
- **Shared where it helps, separate where it must be.** Tokens and truly universal
  primitives can be shared across member web and mobile; surface-specific patterns
  (and the whole ops language) are not force-fit.

### Where it lives
The design system is versioned with the frontends and documented alongside
[Frontend Architecture](../frontend/40-frontend-architecture.md) and
[Mobile Architecture](../frontend/41-mobile-architecture.md). Tokens are the
contract between design and engineering; when a token changes, it changes
everywhere at once.

---

## Anti-patterns (explicitly rejected)

- **Optimistic money confirmation** — showing "paid" before the rail confirms.
  Forbidden; it is a lie (UX-3, P-16).
- **Hidden fees** — burying the platform fee. Forbidden; the fee is a visible
  ledger line (UX-2).
- **Engagement-maximising dark patterns** — nudges that trade the user's calm for
  time-in-app. Wrong product, wrong incentive (UX-6).
- **Raw money strings** — formatting currency inline instead of via the `Money`
  component. A consistency and correctness bug waiting to happen (P-4).
- **One design language stretched across member and ops** — degrades both.

---

*Return to the [Product index](../README.md#1-product), or continue to
[Domain / Domain Model](../domain/10-domain-model.md).*
