# ADR-0027: Attribution, ownership, and the two-register model

- **Status:** Proposed
- **Date:** 2026-07-16
- **Deciders:** Ledger & fund-modelling review
- **Supersedes draft:** an earlier draft of this ADR proposed "ownership
  treatments" (deposit / capital / premium) as the primary abstraction. That
  draft is replaced by this one — the first-principles review below shows those
  are *claim-types*, not ownership, and that the missing primitives are
  attribution and an ownership register.

## Context

The ledger hardwires an assumption that ordinary banking gets away with but
community finance does not:

> **Contributor = Owner = Ledger Position = Economic Interest.**

Each equality is false in real community finance:

- **Contributor ≠ Owner.** Alice pays KES 10,000: 6,000 for herself, 4,000 for
  Bob. Parents pay for children, employers for employees, sponsors for
  beneficiaries, members settle each other's obligations, strangers give to a
  fundraiser. The payer determines *nothing* about ownership.
- **Owner ≠ Ledger Position.** A group business earns KES 100,000. Before the
  group *declares* a distribution, members hold a real economic interest in the
  retained surplus — but there is no per-member ledger balance; the ledger holds
  one **retained-earnings** account. Their interest is *derived*, not posted.
- **Ledger Position ≠ Economic Interest.** In a jointly-owned pool a member owns
  a proportional interest without any individually redeemable balance — exactly
  how a fund beneficiary, a trust beneficiary, or a street-name shareholder
  holds value.

These are not edge cases; they are the definition of pooled, governed money.
The current model — contribution credits the payer's member sub-ledger as an
individual liability — cannot express any of them.

Three bodies of established practice already solve this, and we adopt their
structure rather than re-deriving it:

- **Trust law** separates three roles: **settlor** (payer) / **trustee** (legal
  title) / **beneficiary** (economic interest). Wepl had modelled the first two
  as one and omitted the trustee entirely.
- **Fund accounting** separates the **transfer agent** (a register of who holds
  how many units) from the **fund accountant** (the NAV / general ledger). Two
  books, reconciled. Economic interest = units × NAV, *derived*.
- **Custody / client-money** rules hold pooled cash in one **omnibus** account
  (e.g. a regulated trust account) while beneficial entitlements live in the
  firm's *own* register — proving each client's share of a commingled balance.

Prior art in-market (Malipo Circles, Chamasoft, Stanbic Chama, Chango/M-Changa)
all pick *one* ownership shape per product and never maintain an authoritative
per-member *redeemable* balance in a pooled fund; Malipo holds cash in an NCBA
trust account with official-gated distribution — the omnibus + governed-payout
pattern. Wepl is custodial *and* ledger-authoritative, so it must model the
distinctions they can avoid — which also carries a compliance shadow (holding
individually redeemable balances edges toward deposit-taking; pooled collective
funds look like a trust or a collective-investment scheme — ADR-0026's regulated
capability ceiling).

## Decision

Model value movement as **three planes**, not one linear chain, over **two
registers** anchored to an explicit **custody/legal-title** holder. Economic
interest is **derived, never stored**. Attribution and governance decisions are
**events**, never a second source of truth.

```
POLICY   Governance / the fund's constitution
         defines attribution & distribution rules │ authorizes events
              │                                     │
EVENTS   Payment ─▶ Attribution ─▶ Declaration ─(authorized)─┐
         (append-only command log; nothing here is queried    │
          for "who owns what")                                ▼
STATE    ┌─ Cash / GL ledger        (shillings, double-entry) ┐  one posting
         ├─ Ownership register      (units / sub-claims)      │  chokepoint,
         └─ Custody / legal-title    (trustee + governing doc)┘  per-book invariant
              │
DERIVED  Economic Interest(party, fund) = register_share × NAV   ← a view, not a table
```

### 1. Two orthogonal axes (replacing "ownership treatments")

Ownership (*who*) is independent of claim-type (*what kind of claim*). The old
draft's deposit/capital/premium are **claim-types** — the classic
debt / equity / transfer trichotomy — not ownership.

- **Owner axis:** `individual | collective | organization | trust` (extensible).
- **Claim-type axis:**
  - **debt** — a redeemable liability of a fixed amount ("deposit"). Owed to the
    attributed owner. Ledger position == economic interest.
  - **equity** — a residual, NAV-linked interest ("capital"). Held via the
    ownership register; economic interest derived; crystallised to a liability
    only on declared distribution/redemption.
  - **transfer** — value relinquished, no retained claim ("premium" / expense /
    gift). Owner keeps nothing.

They compose: individual-debt (a savings deposit), collective-equity (an
investment pool's retained surplus), individual-equity (a member's units),
collective-transfer (a welfare premium into the pool), etc.

### 2. Attribution is a first-class **event**, with a vesting lifecycle

Attribution answers the first genuine economic question — *whose position
changes* — and is reused across contributions, distributions, expense
apportionments, sponsorships, transfers, corrections, and ownership conversions.

- Shape: `Attribution{ source_payment?, allocations:[{party, amount|units, vesting}], authorized_by }`.
- Lifecycle: `pledged → vested → posted → (reversible)`. This distinguishes a
  revocable pledge / escrow / conditional sponsorship from an executed transfer
  (gift-law finality) — the gap the old model skipped.
- **Attribution is consumed into postings and then is immutable history.** It is
  *never* queried to answer current ownership — that would create a second book
  and break ADR-0001. The identity attribution (Alice → Alice) is still made
  explicit, so no posting recipe ever assumes `contributor = owner`.

### 3. Two registers, one chokepoint

- **Cash/GL ledger** (existing, unchanged): float, pool control accounts,
  liabilities, equity/retained-earnings, income/expense. Balances derived from
  immutable lines (ADR-0001/0002).
- **Ownership register** (new, added only when needed — see §6): append-only
  unit issuance / transfer / redemption per pool. Units are to this book what
  shillings are to the ledger; it is the transfer-agent function to the GL's
  fund-accountant function.
- `post_journal()` generalises to `post(book, lines)` over
  `book ∈ {cash, register}`, each with its own conservation invariant
  (`Σdebit == Σcredit` for cash; unit-conservation for the register). One door
  (ADR-0004), two invariants. Authorisation (ADR-0007/0009) and attribution
  resolution happen *before* posting, so the engine only sees already-attributed,
  already-authorised lines.

### 4. Custody / legal-title is modelled explicitly

Every pool names a **trustee/custodian** (legal title) and a **governing
document**. This is what makes "collective ownership" legally real, defines *by
whom* a liability is owed, and fixes regulatory posture (trust vs deposit-taking
vs CIS). Trivial to represent today (one row) but not optional.

### 5. Economic interest is derived; crystallisation bridges the books

`economic_interest(party, fund)` is a computed view:
`register_share(party, fund) × NAV(fund)`. For **debt** funds the two books
coincide (the member's liability line *is* their claim). For **equity/collective**
funds they diverge and interest is derived. **Crystallisation** is the named
governance event that converts a derived equity interest into a ledger liability
(`DR retained-earnings / CR member liabilities`, split by a register-share
snapshot) — the exact moment beneficial interest becomes a posted position. This
is also the two-stage external-income flow: income lands collectively as retained
earnings; a *declared* distribution crystallises it to members.

### 6. Graduation trigger — keep the complexity gated

A collective fund starts in **contribution-share** mode (economic interest =
pro-rata of recorded contributions; no unit register). It **graduates** to
**unit/NAV** mode only when *both* hold: the pool carries assets that change in
value over time **and** members enter/exit at different times — the precise
condition under which pro-rata-of-contributions becomes unfair and NAV is
required. ROSCAs and simple savings/welfare funds never graduate.

### 7. The four commitments that prevent a rewrite

Extensibility comes from discipline, not from a perfect taxonomy:

1. **No posting recipe assumes `contributor = owner = position`** — always route
   through an explicit attribution, even the identity map.
2. **Model custody/legal-title now**, even trivially.
3. **Economic interest is a derivation from day one**, even for debt funds where
   it equals the liability.
4. **Add the ownership register only when the graduation trigger fires.**

## Consequences

- **+** Payment, attribution, ownership, economic interest and ledger position
  are cleanly separated; sponsorships, split contributions, third-party
  settlement and pooled beneficial ownership all become expressible.
- **+** The architecture is the century-proven trust + transfer-agent/fund-
  accountant model, so welfare (collective-transfer), goal pools (contribution-
  share), investment chamas (collective-equity → units/NAV), ROSCAs (individual-
  debt, transient) and business income (retained earnings → crystallised
  distribution) all fit one frame.
- **+** Consent + audit on every attribution and crystallisation gives a
  consumer-protection and client-money story competitors avoid by never holding
  individual redeemable balances.
- **+** Economic interest can never drift from truth — it is a view, not a cache
  (ADR-0002 preserved).
- **−** A second book (ownership register) and a second invariant in the posting
  engine, plus NAV/crystallisation machinery — deferred behind the graduation
  trigger, but real when it lands.
- **−** `Account.owner` must generalise from `User` to a polymorphic `Party`
  (User | Organization | Trust) for organization/trust ownership; until then
  those owners have no first-class home and must wait rather than be faked.
- **−** Attribution vesting, custody/legal-title and governing documents are new
  surfaces in fund setup and the contribution flow.
- **−** Real tax/regulatory weight: claim-type is a compliance signal (debt =
  deposit-taking posture; equity = CIS posture; trust custody = client-money
  segregation), gated by the ADR-0026 capability ceiling — not a settings toggle.

## Alternatives considered

- **Keep `contributor = owner = position` (today's model).** Rejected — false for
  split contributions, sponsorships, third-party settlement, collective pools and
  retained earnings; it is the assumption this ADR exists to break.
- **A single linear hierarchy `Payment → … → Governance`.** Rejected — it
  linearises three distinct planes (events / state / policy). Governance both
  gates events *and* supplies the rules that resolve attribution, so it wraps the
  pipeline; it is not merely downstream.
- **Make Economic Interest a stored, first-class value.** Rejected — it rebuilds
  the mutable-balance anti-pattern ADR-0002 removed. Interest is derived from the
  register × NAV.
- **Make Attribution the standing authority on current ownership.** Rejected — a
  second source of truth alongside the ledger breaks ADR-0001. Attribution is an
  event consumed into postings, retained as history, never queried for state.
- **Treat deposit/capital/premium as "ownership treatments."** Rejected — they
  describe the *representation* of a claim (debt/equity/transfer), orthogonal to
  *who* owns it. Conflating them hides the owner axis.
- **Omit custody/legal-title (jump attribution → ledger).** Rejected — beneficial
  ownership is undefined without a legal-title holder; "liability owed to whom /
  by whom" and regulatory posture depend on it.
- **Build full unit/NAV/crystallisation for every fund now.** Rejected — over-
  builds a transfer agency for ROSCAs and simple chamas. Gated behind the
  graduation trigger; the four commitments keep the door open without the cost.
- **Copy Malipo's group-owned-by-default model wholesale.** Rejected as the
  general rule — it is correct for collective-transfer funds (our `premium`) and
  is one owner/claim-type combination, but denying individually-redeemable
  positions to debt and goal-pool funds discards Wepl's ledger-authoritative
  differentiation.
