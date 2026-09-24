# ADR-0027: Attribution, ownership, and the two-register model

- **Status:** Accepted — ownership rules decided 2026-09-24 (§0). The unit
  register and NAV machinery (§3, §5, §6) stay gated behind the graduation
  trigger; accepting this ADR does not build them.
- **Date:** 2026-07-16 (proposed) · 2026-09-24 (accepted)
- **Deciders:** Ledger & fund-modelling review; Harry (product owner) for §0
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

### 0. Who owns a pool — decided 2026-09-24

Four product decisions, taken one at a time against what the code does today.
They settle the *owner* and *claim-type* axes for every community program; the
rest of this ADR is the frame they sit in.

1. **Money paid into a pool belongs to the group.** Each member holds a
   **share**: what they paid in, less their part of what the group has spent,
   plus their part of any distribution the group has declared. A share is a
   claim on the group, realised only by a **group decision** — a payout, an exit
   settlement, or a wind-up — and never withdrawn on demand. A member's
   sub-ledger under the pool control account (`coa.member_fund_account`) *is*
   their share; the account shape does not change, the recipes do.
   A balance a member can withdraw on demand is deposit-taking, which is the
   regulated `deposit.take` capability (`apps/organizations/capabilities.py`)
   and outside the community ceiling. Member-owned redeemable money therefore
   belongs to a licensed archetype (a SACCO), never to a community program.
   ROSCAs are unchanged: a turn draws the whole pot from the recipient's share,
   which goes negative (they owe the group) and returns to zero over a cycle.
2. **Welfare premiums are transfers.** They go into the fund itself and give
   nobody a share or a refund on leaving; a claim is paid from the fund, not
   charged to the claimant. Eligibility ("paid up") is read from the member's
   payment history in the journal, not from a balance. **At wind-up, what is
   left is split per head among members who are paid up at that point**,
   whatever each paid in. The group may vote a different split.
3. **Advance interest belongs to the group.** An emergency advance is the group
   lending its own money: the receivable is a pool asset, and interest credits
   the pool's retained surplus (`coa.retained_surplus_account`), which the group
   shares out when it declares a distribution. Wepl earns nothing from advances.
   A default is set off against the borrower's own share first; the existing
   80% cap (`EmergencyAdvanceService.MAX_ADVANCE_RATIO`) means unpaid principal
   is always covered by it unless group spending has since shrunk the share.
   *Lending at interest still needs legal review before real money* —
   `credit.lend` is outside the community ceiling, yet advances ship to
   communities.
4. **A leaving member gets their full share back**, less any advance they still
   owe. A group may set an exit fee in its own rules; the platform default is
   none. Exit is protected: the group must decide an exit request within
   **30 days**, and a member who is refused is paid at wind-up at the latest.

How the rules play out across every scenario — everyday pools, each fund type,
third-party payers, tenancy and enterprise archetypes, with a worked year for
one group — was walked through with the product owner before deciding.

**What this commits the code to** (none of it built by accepting this ADR; each
is its own change, and each fixes something the ledger answers wrongly today):

| Today | Required |
|---|---|
| A voted disbursement debits the **requester's** share for the whole amount (`contributions/services/disbursement.py`, `_schedule_execution` → `disbursement_lines(member=req.requested_by)`) | Split the cost across funded shares, pro-rata or per head by the group's rule — the shape `record_pool_expense` already posts |
| A welfare claim debits the **claimant's** welfare sub-ledger (`services/welfare.py`, `_disburse`) and premiums credit a per-member liability | Premiums and claims post against the welfare pool itself; no member welfare shares |
| Advance receivable sits under `1200` unlinked to the pool; interest credits `4100 Interest Income` (`posting_map.advance_repayment_lines`) | Receivable owned by the pool; interest credits the pool's retained surplus |
| Leaving a contribution only flips `is_active` (`services/contribution.py`, `leave_contribution`); closing only flips `status` | Exit-settlement, share-transfer (nominee / estate), write-off and wind-up recipes |
| `record_pool_expense` needs only `contribution.admin` | Spending group money follows the group's voting threshold, as a payout does |
| Nothing forbids a path paying a member out of their share without a group decision | A test that fails the build if one appears |

Production still points at the M-Pesa sandbox, so no real balance has to be
restated. That makes now the cheapest moment to change these recipes.

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
    attributed owner. Ledger position == economic interest. *Per §0, redeemable
    on demand only in a program whose organization holds `deposit.take`; in a
    community pool a member's share is realised by group decision.*
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

*Who* holds legal title — Wepl itself, or a licensed partner — is the custody
decision, which gets its own ADR. This section only requires that every pool
names one; today every pool defaults to `CustodyArrangement(trustee_label='Wepl
(platform, in trust)', legal_basis='trust')`.

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

- **+** (§0) Every per-member number the ledger reports becomes true: a group
  spend no longer shows the requester owing the others, a welfare claimant no
  longer shows a debt to the fund, and a member who leaves no longer has a
  balance stranded with no way out.
- **+** (§0) Member-owned redeemable money is gated by the capability layer
  that already exists, so an enterprise archetype (a SACCO) can offer it later
  on the same accounts without a community ever drifting into deposit-taking.
- **−** (§0) Members carry losses inside the group and cannot cash out alone.
  That is how chamas already work; the 30-day exit rule is what stops it
  trapping a minority.
- **−** (§0) Advances stop being a Wepl income source. Wepl's revenue has to
  come from ADR-0024.
- **−** (§0) The app's wording must say "your share", not "your balance" — a
  member reading "balance" would reasonably expect to withdraw it.

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
- **Keep individually-redeemable positions for savings and goal pools.** This
  was the Proposed draft's position, and it rejected Malipo's
  group-owned-by-default model as the general rule. **Reversed in §0 on
  2026-09-24.** No code path ever let a member redeem on demand — every outflow
  was already a group act — so the redeemable claim existed only on the books,
  where it produced wrong per-member numbers. It is also deposit-taking, which
  the capability layer reserves for licensed archetypes. The ledger-authoritative
  differentiation survives: shares are still exact, derived from immutable
  lines, and provable per member.
- **Let each fund choose its ownership model.** Rejected for communities —
  every spending path would need both behaviours built and tested, and the
  redeemable one is regulated. The choice lives at the archetype level instead,
  gated by capability.
- **Advance interest to Wepl (`4100`).** Rejected in §0 — it lends members'
  money and books the return to the platform, which no ADR ever sanctioned.
- **A default exit fee or forfeiture.** Rejected in §0 — members get back what
  is theirs unless their own group's rules say otherwise.
