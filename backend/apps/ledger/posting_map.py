"""
Posting Map — the canonical debit/credit recipe for every money operation.

Each builder returns a *balanced* ``list[Line]`` ready for ``post_journal()``.
Amounts are ``Money``; accounts are resolved through ``coa``. This is the single
place that encodes which accounts each business operation touches, so the P0-05
service rewrite calls these builders instead of hand-rolling journals (and the
recipes are proven balanced by tests_posting_map.py).

Recipe summary (DR / CR):
    contribution            DR 1000 Float          / CR member SL (+ CR 4000 Fee)
    disbursement            DR member SL            / CR 1000 Float
    welfare contribution    DR 1000 Float          / CR member welfare SL
    welfare claim           DR member welfare SL    / CR 1000 Float
    advance disbursement    DR member AR (1200)     / CR 1000 Float
    advance repayment       DR 1000 Float           / CR member AR (+ CR 4100 Interest)
    standing order          (uses the contribution recipe, op_type=STANDING_ORDER)
"""
from __future__ import annotations

from dataclasses import dataclass

from . import coa
from .money import Money
from .models import JournalLine
from .posting import Line

DEBIT = JournalLine.Direction.DEBIT
CREDIT = JournalLine.Direction.CREDIT


class Op:
    """Canonical ``JournalEntry.op_type`` values."""
    CONTRIBUTION         = 'CONTRIBUTION'
    DISBURSEMENT         = 'DISBURSEMENT'
    ROSCA_PAYOUT         = 'ROSCA_PAYOUT'
    WELFARE_CONTRIBUTION = 'WELFARE_CONTRIBUTION'
    WELFARE_CLAIM        = 'WELFARE_CLAIM'
    ADVANCE_DISBURSEMENT = 'ADVANCE_DISBURSEMENT'
    ADVANCE_REPAYMENT    = 'ADVANCE_REPAYMENT'
    SHARES_PURCHASE      = 'SHARES_PURCHASE'
    STANDING_ORDER       = 'STANDING_ORDER'
    POOL_EXPENSE         = 'POOL_EXPENSE'
    EXTERNAL_INCOME      = 'EXTERNAL_INCOME'
    SURPLUS_DISTRIBUTION = 'SURPLUS_DISTRIBUTION'
    FEE                  = 'FEE'
    ADJUSTMENT           = 'ADJUSTMENT'


def _require_positive(m: Money, what: str) -> None:
    if not isinstance(m, Money):
        raise TypeError(f"{what} must be a Money, got {type(m).__name__}")
    if not m.is_positive:
        raise ValueError(f"{what} must be positive, got {m}")


@dataclass(frozen=True)
class Allocation:
    """One beneficiary's attributed share of a contribution (ADR-0027).

    ``member`` is the *owner* the value is attributed to — not necessarily the
    payer. ``amount`` is the net credited to that member's liability sub-ledger.
    Payment answers "who paid"; attribution answers "whose position changes",
    and they are different questions.
    """
    member: object
    amount: Money


def attributed_contribution_lines(*, fund_type, fund_id,
                                  allocations: list[Allocation],
                                  fee: Money | None = None) -> list[Line]:
    """A contribution whose ownership is *attributed* across one or more
    beneficiaries, independent of who paid (ADR-0027).

    Cash arrives in float for the gross (Σ allocations + fee); each beneficiary's
    liability sub-ledger is credited its attributed share; the optional fee is
    platform revenue. The single-beneficiary case (the payer owns all of it) is
    the *same* code path with one allocation — so no recipe ever silently assumes
    ``contributor == owner``; the identity attribution is made explicit.
    """
    if not allocations:
        raise ValueError("attributed contribution needs at least one allocation")
    currency = allocations[0].amount.currency
    fee = fee or Money.zero(currency)
    net_total = Money.zero(currency)
    for alloc in allocations:
        _require_positive(alloc.amount, "allocation amount")
        net_total = net_total + alloc.amount            # currency-checked by Money
    gross = net_total + fee
    _require_positive(gross, "contribution gross")
    lines = [Line(coa.mpesa_float_account(), DEBIT, gross.amount, note="contribution in")]
    for alloc in allocations:
        member_acct = coa.member_fund_account(
            user=alloc.member, fund_type=fund_type, fund_id=fund_id)
        lines.append(Line(member_acct, CREDIT, alloc.amount.amount, note="member contribution"))
    if fee.is_positive:
        lines.append(Line(coa.fee_revenue_account(), CREDIT, fee.amount, note="platform fee"))
    return lines


def contribution_lines(*, member, fund_type, fund_id, gross: Money,
                       fee: Money | None = None) -> list[Line]:
    """Member pays ``gross`` in (cash arrives in float). ``fee`` (optional) is
    platform revenue; the remainder increases the member's liability balance.

    This is the identity-attribution case of ``attributed_contribution_lines``:
    the payer is the sole beneficiary. Routing it through the attributed builder
    keeps ``contributor == owner`` an explicit choice, never an assumption
    (ADR-0027)."""
    _require_positive(gross, "contribution amount")
    fee = fee or Money.zero(gross.currency)
    net = gross - fee
    _require_positive(net, "net contribution (gross minus fee)")
    return attributed_contribution_lines(
        fund_type=fund_type, fund_id=fund_id,
        allocations=[Allocation(member=member, amount=net)], fee=fee,
    )


def disbursement_lines(*, member, fund_type, fund_id, amount: Money) -> list[Line]:
    """Pay ``amount`` out to a member, drawing down their liability balance."""
    _require_positive(amount, "disbursement amount")
    member_acct = coa.member_fund_account(user=member, fund_type=fund_type, fund_id=fund_id)
    return [
        Line(member_acct, DEBIT, amount.amount, note="disbursement"),
        Line(coa.mpesa_float_account(), CREDIT, amount.amount, note="cash out"),
    ]


def reallocate_to_org_lines(*, member, org, fund_type, fund_id,
                            amount: Money) -> list[Line]:
    """Transfer a member's position in a fund to an organization (ADR-0027
    ownership reallocation): debit the member's sub-ledger, credit the org's. A
    pure change of *who owns the claim* — no cash moves, and since both are
    fund liabilities the pool total is unchanged. A governed money movement (it
    removes a member's redeemable claim), so it runs through post_journal like
    any other."""
    _require_positive(amount, "reallocation amount")
    member_acct = coa.member_fund_account(user=member, fund_type=fund_type, fund_id=fund_id)
    org_acct = coa.org_fund_account(org=org, fund_type=fund_type, fund_id=fund_id)
    return [
        Line(member_acct, DEBIT, amount.amount, note="reallocate to org"),
        Line(org_acct, CREDIT, amount.amount, note="org position"),
    ]


def pool_expense_lines(*, fund_type, fund_id,
                       allocations: list[Allocation]) -> list[Line]:
    """A collective pool expense apportioned across members (ADR-0027 goal-pool):
    each member's liability sub-ledger is debited its share; cash leaves float for
    the total. The debit-side mirror of ``attributed_contribution_lines`` — money
    a jointly-owned pool spends is borne by members in proportion to the shares
    the caller computed (pro-rata of position, per-capita, …)."""
    if not allocations:
        raise ValueError("pool expense needs at least one allocation")
    currency = allocations[0].amount.currency
    total = Money.zero(currency)
    lines: list[Line] = []
    for alloc in allocations:
        _require_positive(alloc.amount, "expense share")
        total = total + alloc.amount                    # currency-checked by Money
        member_acct = coa.member_fund_account(
            user=alloc.member, fund_type=fund_type, fund_id=fund_id)
        lines.append(Line(member_acct, DEBIT, alloc.amount.amount, note="pool expense share"))
    _require_positive(total, "pool expense total")
    lines.append(Line(coa.mpesa_float_account(), CREDIT, total.amount, note="pool expense out"))
    return lines


def external_income_lines(*, fund_id, amount: Money) -> list[Line]:
    """Business / external proceeds into a pool (ADR-0027): cash arrives in float
    and is owned *collectively* as the pool's retained surplus. No member position
    changes — attribution to individuals is a separate, declared act."""
    _require_positive(amount, "external income")
    return [
        Line(coa.mpesa_float_account(), DEBIT, amount.amount, note="external income in"),
        Line(coa.retained_surplus_account(fund_id=fund_id), CREDIT, amount.amount,
             note="retained surplus"),
    ]


def distribute_surplus_lines(*, fund_id, allocations: list[Allocation]) -> list[Line]:
    """A declared distribution of retained surplus to members (ADR-0027): draws
    down the collective equity and *crystallises* it into each member's redeemable
    contribution position by the declared share. The exact moment a derived
    beneficial interest becomes a posted liability."""
    if not allocations:
        raise ValueError("distribution needs at least one allocation")
    currency = allocations[0].amount.currency
    total = Money.zero(currency)
    credits: list[Line] = []
    for alloc in allocations:
        _require_positive(alloc.amount, "distribution share")
        total = total + alloc.amount                    # currency-checked by Money
        member_acct = coa.member_fund_account(
            user=alloc.member, fund_type='contribution', fund_id=fund_id)
        credits.append(Line(member_acct, CREDIT, alloc.amount.amount, note="surplus distribution"))
    _require_positive(total, "distribution total")
    return [Line(coa.retained_surplus_account(fund_id=fund_id), DEBIT, total.amount,
                 note="distribute surplus")] + credits


def welfare_contribution_lines(*, member, fund_id, amount: Money) -> list[Line]:
    return contribution_lines(member=member, fund_type='welfare', fund_id=fund_id, gross=amount)


def welfare_claim_lines(*, member, fund_id, amount: Money) -> list[Line]:
    return disbursement_lines(member=member, fund_type='welfare', fund_id=fund_id, amount=amount)


def advance_disbursement_lines(*, member, advance_id, principal: Money) -> list[Line]:
    """Disburse an emergency advance: the member now owes ``principal`` back, so a
    receivable (asset) is recognised against the cash that leaves the float."""
    _require_positive(principal, "advance principal")
    ar = coa.member_receivable_account(user=member, fund_id=advance_id)
    return [
        Line(ar, DEBIT, principal.amount, note="advance receivable"),
        Line(coa.mpesa_float_account(), CREDIT, principal.amount, note="advance paid out"),
    ]


def advance_repayment_lines(*, member, advance_id, principal: Money,
                            interest: Money | None = None) -> list[Line]:
    """Member repays an advance: cash in, clear the receivable, recognise any
    interest as income. Either portion may be zero (e.g. a pure-interest or
    pure-principal payment), but the total must be positive."""
    interest = interest or Money.zero(principal.currency)
    if principal.is_negative or interest.is_negative:
        raise ValueError("repayment principal/interest must be non-negative")
    total = principal + interest
    _require_positive(total, "repayment total")
    ar = coa.member_receivable_account(user=member, fund_id=advance_id)
    lines = [Line(coa.mpesa_float_account(), DEBIT, total.amount, note="repayment in")]
    if principal.is_positive:
        lines.append(Line(ar, CREDIT, principal.amount, note="clear receivable"))
    if interest.is_positive:
        lines.append(Line(coa.interest_income_account(), CREDIT, interest.amount, note="interest"))
    return lines
