# Domain / 13 — Governance Architecture

> How a community decides and acts *collectively* — and how the software **enforces**
> those decisions rather than merely recording them. Governance is the mechanism by
> which Wepl replaces "trust the treasurer" with "trust the rules the group agreed
> to," which is the whole point of the [Vision](../product/01-vision.md).

Grounded in [ADR-0009](../../adr/0009-centralized-authorization-policy.md) and
[ADR-0011](../../adr/0011-community-ownership-and-lifecycle.md); realised across
`apps/communities` and the centralized `FinancialPermissions` policy.

---

## Why governance is a first-class concern

In informal collective finance, the treasurer *is* the governance: they decide who
gets paid, when, and how much, and the group's only recourse is trust. That single
point of authority is exactly the failure mode Wepl exists to remove. So authority
in Wepl is **decomposed into permissioned, auditable operations gated by collective
consent** — no single person holds the power the treasurer held, and the group's
agreed rules, not a person's discretion, decide what happens.

## The two questions governance answers

1. **May this actor do this action?** — *authorization* (individual authority /
   role).
2. **Has the group consented to this action?** — *collective decision* (votes,
   thresholds, quorum).

Privileged money actions require **both**: an authorized proposer *and* the group's
consent at the configured threshold. Neither alone is sufficient for the actions
that matter (payouts, rule changes).

## Authorization is centralized (ADR-0009)

Authorization is **not** re-implemented per view. It lives in one policy layer:

- **Money authority** runs through `FinancialPermissions` — the single place that
  answers "may this member move/authorize this money in this community?"
- **Operator authority** (staff) runs through the capability map and
  `RequireCapability` (see [Identity Architecture](14-identity-architecture.md)).

**P-13** demands this centralization because scattered authorization is
authorization that will *eventually be forgotten* in some new endpoint — and a
forgotten money-authorization check is a breach. One policy layer means one place to
audit, one place to change, and one place a reviewer must look.

## Collective decisions: proposals, votes, thresholds, quorum

A privileged action is expressed as a **proposal** the community votes on. The
model carries:

- **Voting threshold** — configurable per community/fund: *admins-only*, *25%*,
  *50%*, or *100%* of members (as seen in the contribution model's
  `VOTING_THRESHOLD_CHOICES`).
- **Quorum** — the minimum participation for the vote to bind, so a handful of
  members cannot move the group's money on a sleepy day.
- **Tally and outcome** — the running count and the terminal decision.

The invariant: **a privileged action cannot execute until its proposal has met its
threshold and quorum.** The gate is checked at the authorization layer, not left to
the UI. The UI's job is only to make the decision *legible*
([UX-5](../product/06-ux-and-design.md)) — to show the why, the threshold, and the
tally — never to be the enforcement.

## Governance gates money at the one door

The elegance of the ledger-first design shows here. Because all money moves through
`post_journal()` (**P-2**) and all money authority runs through one policy
(**P-13**), governance has **one place to gate money**: the authorization check that
precedes a payout's posting. A payout that lacks the group's consent simply never
reaches `post_journal()`. There is no back route, because there is no second money
door.

This is why [User Journey J4 (Payout)](../product/05-user-journeys.md) can state
flatly that "a payout that is not authorized by governance *cannot* post" — it is a
structural guarantee, not a policy that each feature must remember to honour.

## Deadlock, quorum failure, and safety

Collective decision systems can deadlock — a quorum that can never be reached, a
tie that never breaks, a proposal that strands money. The audit noted Wepl's
"sophisticated quorum/deadlock governance" as a genuine strength. The design
principles:

- **No action stranded forever.** Thresholds and quorums have defined resolution
  paths (timeouts, admin-tier fallbacks where the rules permit) so a fund cannot be
  frozen by inaction.
- **Safety over liveness for money-out.** When in doubt, the safe default is *not to
  disburse* — an un-made payout is recoverable; a wrong one is a trust breach.
- **Every governance outcome is recorded immutably**, so the group can always see
  how a decision was reached.

## Community lifecycle and ownership (ADR-0011)

Governance presupposes a well-defined community: it always has an **owner**, an
explicit **lifecycle state**, and members with explicit **status** (including
modelled *rejoin*, not a faked new row). Ownership and lifecycle are first-class so
that "who ultimately controls this community" is never ambiguous — an ambiguity that
would undermine every governance decision built on top of it.

## Governance as an immutable record

Consistent with the platform's signature pattern
([Domain Model §Cross-cutting truths](10-domain-model.md)), governance decisions are
recorded immutably: the proposal, the votes, and the outcome form an auditable
trail. A member can always answer "who agreed to this, and when?" — the collective
analogue of being able to answer "where did the money go?"

## What governance deliberately does *not* do

- **It does not hold money.** Governance authorizes; the ledger records. A vote's
  outcome is an input to an authorization check, not a mutation of a balance.
- **It does not live in the UI.** The threshold gate is server-side policy; the UI
  only renders it.
- **It does not vary per endpoint.** One centralized policy (**P-13**), so a new
  money endpoint inherits the same governance gate rather than re-inventing (and
  possibly mis-implementing) it.

---

## Future evolution

- **Richer governance primitives** for formal SACCOs (weighted votes by shares,
  delegated authority, multi-signatory payouts) drop in as extensions to the
  centralized policy — not as per-feature logic.
- **Governance events feed the outbox** like everything else, so notifications
  ("your vote is needed", "the payout was approved") are durable and idempotent
  (**P-9**).

---

*Continue to [Identity Architecture](14-identity-architecture.md). See also
[Security Architecture](../architecture/25-security-architecture.md) for how
authorization is enforced at the API edge.*
