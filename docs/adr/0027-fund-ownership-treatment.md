# ADR-0027: Fund ownership treatment — a declared, consented property of every fund

- **Status:** Proposed
- **Date:** 2026-07-16
- **Deciders:** Ledger & fund-modelling review

## Context

The ledger hardwires one interpretation of a contribution: money paid into a
fund credits the payer's **member sub-ledger** (`coa.member_fund_account`, a
LIABILITY under the `2000/2100/2200` payable heads), and a member's "position"
is that credit balance. `disbursement_lines` pays it back out. This is the
**deposit** interpretation — the platform owes the member their money — and it
is treated as a fact of nature.

It is not a fact of nature. It is one of several possible interpretations, and
the wrong one for a growing set of real scenarios surfaced in review:

1. **Welfare** contributions are sunk *premiums* that fund *others'* claims —
   the contributor holds no redeemable claim. Modelling them as an individual
   liability overstates every member's position.
2. **Goal pools** (a family raises an open, member-set amount over a year toward
   a shared event, then spends it collectively on multiple external expenses)
   are jointly owned. Each member's live stake is a *pro-rata share of the net
   pool*, not their gross contributions, and collective spending must be borne
   pro-rata — there is no per-member recipe for this today.
3. **External income** — a group runs a business and deposits the proceeds
   straight into the pool. *Nobody contributed it in*, so no member sub-ledger
   can honestly claim it by attribution. It belongs to the collective as
   **retained earnings**, distributable to members only when the group
   *declares* a distribution by its own rule. The ledger has no income/equity
   representation at the pool level to hold this — only member-payable liability.
4. **Capital** — a member's payment into an investment pool may buy an ownership
   *share* of an enterprise (equity), not a redeemable deposit; returns come via
   distribution, not principal withdrawal.

Two facts about the current schema frame the decision:

- `Account.owner` is a FK to **User only** (`ledger/models.py:281`). An account
  is owned by a natural person or is **owner-less** (`owner=None`). The
  owner-less **pool control account** (ADR-0025 Part B, `coa.pool_account`,
  parented under a LIABILITY head) already exists and is the mechanism for money
  held collectively — but there is no way to make an account owned by an
  **organization** as a legal counterparty (ADR-0026).
- `fund_balance` sums *all* accounts in a fund — member sub-ledgers **and** the
  pool control account — so a collective credit balance is already
  representable; what is missing is (a) an income/equity flavour distinct from
  member liability, and (b) a *declared rule* that says which interpretation a
  given fund uses.

**Prior art.** Kenyan chama platforms resolve this by hardcoding *one*
treatment per product and never maintaining an authoritative per-member
*redeemable* balance. Malipo Circles holds pooled money in a regulated **NCBA
trust account**, records who contributed how much (a *record*, not a redeemable
balance), and lets elected **officials** approve withdrawals to the *chama's own
bank account* — i.e. money is group-owned, distribution is a governed act, and
its "circle types" (investment chama / fundraising / P2P lending) are a coarse,
hardcoded precursor to a declared-treatment axis. Chamasoft is a record-keeper
over the group's own bank account (custody elsewhere, entitlement crystallised
at declared dividend); Stanbic Chama makes the *group* the legal accountholder;
Chango / M-Changa define the pot as goal-owned from the start. None run a
double-entry ledger-of-record that natively distinguishes individual, collective
and organization claims. That distinction is exactly what Wepl is custodial and
ledger-authoritative enough to need — and it carries a **compliance shadow**:
holding individually redeemable balances edges toward deposit-taking, while
pooled collective funds look like a trust (ADR-0026's regulated-capability
ceiling).

## Decision

**Ownership treatment is a declared, consented property of each fund — not an
implicit default.** A fund declares, at creation, how a contribution into it is
owned; that single declaration determines the contribution recipe, the
external-income recipe, whether individual positions exist, and how "position"
is presented. Reallocating value between owners is a first-class, governed money
movement, never a silent mutation.

### 1. Three contribution treatments

Each fund declares one `ownership_treatment`:

| Treatment | Contribution posts | Member position | Redeemable? | Normal account |
|-----------|--------------------|-----------------|-------------|----------------|
| **deposit** | `CR member sub-ledger` | their own balance | yes — it is their money | LIABILITY (`2000`-family) |
| **capital** | `CR member capital account` (units @ NAV) | a *share* of the enterprise | no principal; exit via distribution/buy-back | EQUITY (`3100`-family, new) |
| **premium** | `CR pool control` | **none** — it is the group's | no — sunk | LIABILITY collective (`2100`) |

The *same* KES-1,000 contribution means three different things under three
declared rules. `deposit` is the current behaviour and stays the default for
contribution/ROSCA/goal-pool funds; `premium` is welfare; `capital` is
investment pools.

### 2. Instrument taxonomy (four kinds, each with its own position semantics)

Ownership treatment composes with the fund's *instrument*, which governs
lifecycle and payout shape:

| Instrument | Treatment | Position | Collective spend |
|------------|-----------|----------|------------------|
| **ROSCA** | deposit | transient net (may go negative through a cycle) | n/a — pays individuals in rotation |
| **Welfare** | premium | none | rule-based claims from the pool |
| **Shares** | capital | units × NAV | dilutes NAV |
| **Goal pool** | deposit | **pro-rata of net pool (refundable)** | **apportioned across members** |

`fund_type` generalises to carry the instrument + treatment (aligns with the
`Program` spine, ADR-0026 §2). No `if instrument == …` branches in domain logic;
the fund's declared treatment selects the posting recipe.

### 3. The ownership axis — who can own a position

A ledger position may be owned by:

- **individual** — `owner=User` member sub-ledger (existing).
- **collective** — `owner=None` pool control account (existing, ADR-0025).
- **organization** — an account owned by an `organizations.Organization` as a
  legal counterparty. **Deferred**: requires generalising `Account.owner` from
  `User` to a participant (User *or* Organization). `tenant` is a *partition*,
  not an owner, and must not be overloaded for this. The GL representation
  (below) lands now; the polymorphic owner lands only when a concrete
  org-counterparty scenario exists (inter-community settlement, a registered
  entity as a fund member). Naming it here keeps the door open without building
  speculatively.

### 4. External income → retained earnings → declared distribution (two stages)

Money entering a pool from outside (business proceeds, trust-account interest)
is **income**, not a member liability, and posts in two governed stages:

- **Stage 1 — receipt (collective).** `DR 1000 Float / CR pool retained surplus`
  (`3200`-family, new EQUITY head, owner-less or org-owned). No member position
  moves; the group owns it. Members hold only an *implicit* pro-rata interest.
- **Stage 2 — declared distribution.** A separate, authorised decision:
  `DR pool retained surplus / CR each member sub-ledger` by the fund's sharing
  rule (`equal | pro_rata_capital | pro_rata_units | agreed_ratios`). Only now do
  individuals gain redeemable claims. Undistributed surplus stays on `3200` as a
  group reserve.

Contributions are one-stage (attribution is a fact — the member paid in);
external income is two-stage (attribution is a governance act).

### 5. Reallocation is a governed money movement

Every move of value between owners — member→collective, collective→member
(distribution), member→organization, apportioning a collective expense across
members — is:

- a canonical `posting_map` recipe through `post_journal()` (ADR-0004) — never
  hand-rolled;
- run through `enforce_controls` (ADR-0007) — it debits a redeemable claim, so
  it is subject to the same limits/holds as a payout, including a member's
  FREEZE/closure state;
- **authorised** — either member consent captured at contribution time (the
  declared treatment the member agreed to) *or* an explicit governance decision
  (maker-checker via the approvals registry) — and **audited** (ADR-0019);
- never silent. Converting an individual's redeemable claim into collective or
  organization ownership is member-facing and consent-gated — this is a
  consumer-protection rule, not only an accounting one.

New posting-map builders (Phase target): `goal_pool_expense_lines(apportion=…)`,
`distribute_surplus_lines(apportion=…)`, `reallocate_to_collective_lines`,
`external_income_lines`. Existing `contribution_lines` / `disbursement_lines`
become the `deposit`-treatment recipes.

### 6. The invariant that survives all of this

There is always **exactly one authoritative, ledger-derived answer** to "what is
this participant's economic interest," replayed from immutable journal lines
(ADR-0001/0002). Treatments change *where* that answer lives (member liability,
member capital units, collective pool, retained surplus) and *how* it is
presented — never whether it is derived. Units/NAV, when introduced, are
ledger-native (issued/redeemed through `post_journal`, NAV derived from pool
assets), never a mutable counter.

## Consequences

- **+** Welfare, goal pools, business income and investment capital each get a
  correct model instead of being forced into member-liability; positions stop
  lying for three whole fund classes.
- **+** The collective-withdrawal problem dissolves: goal-pool expenses apportion
  across members (positions stay truthful and self-reconciling); external income
  and its distribution are explicit, governed, two-stage flows.
- **+** "Position" becomes honestly typed — a redeemable balance, a capital
  stake, or "contributed to the collective, no personal claim" — and the mobile
  / console surfaces can present each correctly.
- **+** Consent + audit on any ownership change gives a consumer-protection and
  compliance story competitors (group-owned-by-default) do not have to tell,
  because they never hold individual redeemable balances.
- **−** New EQUITY GL heads (`3100` contributed capital, `3200` retained
  surplus) and their pool-level control accounts; `seed_coa`, reconciliation and
  the CI coverage floor extend to cover them.
- **−** `fund_type` must carry treatment + instrument, and funds need a
  creation-time declaration + a member-visible disclosure at contribution —
  new surface in fund setup and in the contribution flow.
- **−** Organization-owned positions are named but not built; until
  `Account.owner` is generalised, an org-counterparty claim has no first-class
  home and must wait rather than be faked on a pseudo-User.
- **−** Capital/units and retained-earnings distribution have real tax and
  regulatory weight (deposit-taking vs. collective-investment posture); the
  declared treatment is also a compliance signal, gated by the ADR-0026
  capability ceiling — not a free settings toggle.

## Alternatives considered

- **Keep the single deposit/liability model.** Rejected — it mis-states welfare
  (premiums as claims), cannot express jointly-owned goal pools, and has nowhere
  to put external income except a member's sub-ledger it never funded.
- **Do away with member positions entirely; represent all stake as shares.**
  Rejected — it flattens the instrument axis. ROSCA needs transient per-member
  positions; goal pools need refundable individual claims. Unitising a rotating
  credit fund or a redeemable savings pot is the wrong instrument, and a
  "pass-through" sub-ledger cannot carry a non-zero derived balance yet be
  declared meaningless without either an offsetting real account (which is just
  the collective treatment) or off-ledger truth (which ADR-0002 forbids).
- **Distribute every external inflow to members immediately, pro-rata.**
  Rejected — it fabricates attribution the group has not decided and pre-empts
  the governance act. Income is collective until *declared* distributed; the
  two-stage flow keeps the decision explicit and auditable.
- **Overload `tenant` as the "organization owner" of collective money.**
  Rejected — `tenant` is an isolation/partition boundary (ADR-0008), not a
  claimant. Conflating them corrupts both RLS semantics and the meaning of a
  balance. Organization ownership gets a real (deferred) `Account.owner`
  generalisation instead.
- **Copy Malipo's group-owned-by-default model.** Rejected as the *general*
  rule — it is correct for premium/fundraising funds and is exactly our
  `collective` treatment, but denying individually-redeemable positions to
  deposit and goal-pool funds throws away Wepl's ledger-authoritative
  differentiation. We adopt it as *one* declared treatment, not the only one.
