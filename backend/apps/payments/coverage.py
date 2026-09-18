"""PaymentIntent coverage of rail-backed FinancialTransactions (ADR-0030 Slice A).

Before ``PaymentIntent`` can become **authoritative** for the rail dimension — and
before FT's ``mpesa_*`` columns can be dropped — every FT that moved money over a
rail must actually *have* an intent, carrying the same correlation id and receipt.
Intents are populated best-effort today (ADR-0014 wires them at the provider
chokepoints inside ``try/except`` so payment bookkeeping can never break the money
path), so coverage is an open question, not a given.

This module answers it. It is **read-only**: it reports, it never writes and never
repairs. A backfill (if the report says one is needed) is a separate, deliberate
step.

Definitions
-----------
*Rail-backed*  an FT carrying any rail evidence of its own — a checkout id, a
               conversation id, or a receipt. Internal movements (no rail leg)
               are correctly intent-less and are excluded.
*Covered*      that FT has at least one linked ``PaymentIntent``.
*Mismatched*   it has one, but the intent's ``provider_ref``/``receipt``
               disagrees with the FT's columns — coverage without agreement,
               which would silently change reads at cutover.
"""
from __future__ import annotations

from django.db.models import Q

# An FT has a rail leg if any of these carry a value (they are null=True/blank).
_RAIL_EVIDENCE = (
    ~Q(mpesa_conversation_id__isnull=True) & ~Q(mpesa_conversation_id='')
    | ~Q(mpesa_checkout_id__isnull=True) & ~Q(mpesa_checkout_id='')
    | ~Q(mpesa_receipt__isnull=True) & ~Q(mpesa_receipt='')
)


def rail_backed_transactions():
    """Every FT with a rail leg of its own, intents prefetched."""
    from apps.ledger.models import FinancialTransaction
    return (FinancialTransaction.objects
            .filter(_RAIL_EVIDENCE)
            .prefetch_related('payment_intents'))


def _mismatches(ft, intents) -> list[str]:
    """Where an intent exists but disagrees with the FT's own rail columns."""
    out = []
    refs = {i.provider_ref for i in intents if i.provider_ref}
    receipts = {i.receipt for i in intents if i.receipt}

    ft_ref = ft.mpesa_conversation_id or ft.mpesa_checkout_id or ''
    if ft_ref and refs and ft_ref not in refs:
        out.append(f"provider_ref {sorted(refs)} != FT {ft_ref!r}")
    if ft.mpesa_receipt and receipts and ft.mpesa_receipt not in receipts:
        out.append(f"receipt {sorted(receipts)} != FT {ft.mpesa_receipt!r}")
    return out


def intent_coverage(*, sample: int = 20) -> dict:
    """Report PaymentIntent coverage over rail-backed FTs.

    Returns counts plus a bounded sample of the problem rows, so the caller can
    decide whether a backfill is needed before the Slice A cutover.
    """
    total = covered = uncovered = mismatched = 0
    uncovered_by_op: dict[str, int] = {}
    uncovered_by_state: dict[str, int] = {}
    uncovered_sample: list[dict] = []
    mismatch_sample: list[dict] = []

    for ft in rail_backed_transactions().iterator(chunk_size=500):
        total += 1
        intents = list(ft.payment_intents.all())

        if not intents:
            uncovered += 1
            uncovered_by_op[ft.op_type] = uncovered_by_op.get(ft.op_type, 0) + 1
            uncovered_by_state[ft.state] = uncovered_by_state.get(ft.state, 0) + 1
            if len(uncovered_sample) < sample:
                uncovered_sample.append({
                    'ft_id': ft.id, 'op_type': ft.op_type, 'state': ft.state,
                    'conversation_id': ft.mpesa_conversation_id or '',
                    'checkout_id': ft.mpesa_checkout_id or '',
                    'receipt': ft.mpesa_receipt or '',
                })
            continue

        covered += 1
        problems = _mismatches(ft, intents)
        if problems:
            mismatched += 1
            if len(mismatch_sample) < sample:
                mismatch_sample.append({'ft_id': ft.id, 'problems': problems})

    pct = round(covered / total * 100, 2) if total else None
    return {
        'total_rail_backed': total,
        'covered': covered,
        'uncovered': uncovered,
        'coverage_pct': pct,          # None when there is nothing to measure
        'mismatched': mismatched,
        'uncovered_by_op_type': uncovered_by_op,
        'uncovered_by_state': uncovered_by_state,
        'uncovered_sample': uncovered_sample,
        'mismatch_sample': mismatch_sample,
        # No rail-backed FTs at all means this database cannot answer the
        # question (an empty dev DB, or the wrong target) — deliberately NOT the
        # same as "ready", so an empty run can never green-light the cutover.
        'no_data': total == 0,
        # Authoritative only when every rail-backed FT has an agreeing intent —
        # and only when there was something to check.
        'ready_for_cutover': total > 0 and uncovered == 0 and mismatched == 0,
    }
