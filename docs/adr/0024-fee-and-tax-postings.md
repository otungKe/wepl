# ADR-0024: Fee, excise-duty and withholding postings

- **Status:** Proposed
- **Date:** 2026-07-09
- **Deciders:** Architecture review (pending business/compliance inputs)

## Context

The double-entry ledger (ADR-0001) already represents every movement as balanced
`JournalLine`s across the Chart of Accounts, and Transaction 360 surfaces those
debits and credits for every transaction. But today's posting recipes model
**principal only** for the live flows:

- `contribution_lines()` *supports* an optional `fee` that credits `4000 Fee
  Revenue`, but the services do not charge one, so a deposit posts two lines
  (`DR 1000 Float / CR member sub-ledger`).
- There is **no tax modelling**. A real money operation in Kenya charges a fee on
  many operations and owes **excise duty** on that fee/commission to the KRA, and
  in some cases **withholding tax** — money the platform *collects on behalf of a
  tax authority and must remit*, i.e. a liability, never income.

A withdrawal, in the target state, should post the full breakdown an operator (and
an auditor, and the regulator) expects:

```
DR  member sub-ledger              1000.00
CR  1000 M-Pesa Float                985.00   (net paid to the customer)
CR  4000 Fee Revenue                  12.75   (platform income)
CR  2300 Excise Duty Payable           2.25   (owed to KRA — a liability)
```

Amounts must always balance, and the tax lines must be a **liability** (owed
onward), not revenue. The same shape applies to any op type that carries a
charge — deposit, payout, advance, shares — so the policy must be centralised,
not copy-pasted into each recipe.

## Decision

1. **New Chart-of-Accounts liability accounts** (money held for authorities, a
   liability until remitted; codes provisional):
   - `2300` **Excise Duty Payable** (LIABILITY)
   - `2310` **Withholding Tax Payable** (LIABILITY)
   These are GL accounts (no sub-ledger); a later remittance flow debits them when
   the platform pays the authority, clearing the liability.

2. **A single fee/tax posting policy** — one function (e.g.
   `charge_component(gross_fee) -> list[Line]`) that, given a charged fee, returns
   the balanced split: net `4000 Fee Revenue` + `2300 Excise Duty Payable` (+
   `2310` withholding where applicable), computed from configured rates. Every
   posting-map recipe that charges a fee composes this helper, so the full
   breakdown appears consistently and there is exactly one place tax logic lives.
   `post_journal()` (ADR-0004) remains the only door; this only shapes the lines.

3. **Rates as configuration, default zero.** A `FeeSchedule` (per op type: flat /
   percentage / tiered) and tax rates (excise, withholding) live in config — a
   settings block first, a small admin-editable table later. **Defaults are 0**,
   so shipping the accounts + policy changes no journal until rates are set. This
   lets us land the structure now and switch it on when the numbers are approved.

4. **Design-first (this ADR), then implement.** Per the current decision, the
   accounts, the policy helper, and the recipe wiring are implemented only once
   the business/compliance inputs below are provided — this ADR fixes the shape
   so the implementation is mechanical.

## Open questions (business & compliance — required before implementation)

1. **Which operations charge a fee**, and the **fee schedule** for each
   (contribution / withdrawal / disbursement / ROSCA payout / advance / shares) —
   flat, percentage, or tiered, and the amounts.
2. **Excise duty** — the rate and its **base** (levied on the *fee/commission*,
   not the principal). Is the displayed fee **inclusive** of excise (we back out
   the duty) or is excise **added on top**?
3. **Withholding tax** — does it apply, on what, and at what rate?
4. **Who bears the fee** — deducted from the customer's amount (they receive net),
   or added on top of what they requested?
5. **Rounding** — rounding rule and minor-unit handling for the tax split
   (amounts must still sum exactly; see ADR-0003 `Money`).
6. **Remittance cadence** to the authority (informs the later settlement flow that
   clears `2300`/`2310`).

## Consequences

- **+** Every transaction's journal shows the complete, regulator-grade breakdown
  (principal, net, fee income, taxes owed) — already surfaced by Transaction 360.
- **+** Taxes are modelled as liabilities, so the platform can prove at any time
  what it owes the authority and reconcile remittances.
- **+** One central policy; adding a charge to a new op type is one line.
- **−** Requires business/compliance sign-off on rates before it can be switched
  on; wrong rates are a compliance risk, hence config + zero defaults.
- **−** A remittance/settlement flow (debit the payable when paid to KRA) is
  additional future work, adjacent to OP-6 Treasury.

## Alternatives considered

- **Bake tax into each recipe.** Rejected — duplicates rate logic across six
  recipes; drift and audit risk. A single policy helper is the ADR-0004 spirit.
- **Treat excise as contra-revenue (net the fee).** Rejected — understates both
  income and the liability owed to the authority; a tax collected on behalf of
  KRA is a liability, and the gross fee is real income.
- **Store tax as metadata on the movement, not journal lines.** Rejected — it
  would not appear in the trial balance or prove conservation; taxes are money and
  must be in the ledger (ADR-0001).
