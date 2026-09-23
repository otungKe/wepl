"""PaymentIntent coverage of rail-backed FinancialTransactions (ADR-0030).

``PaymentIntent`` is now the rail record: FT's ``mpesa_*`` columns are gone and
the payout path mints an intent before it calls the rail. The **payout** side is
therefore covered by construction. The **collection** side is not — the STK
chokepoint mints its intent with no ``financial_transaction`` and nothing ever
fills it in, and the paybill (C2B) path never had an initiation to record at all.

This module measures that remaining gap. It is **read-only**: it reports, it
never writes and never repairs. A backfill is a separate, deliberate step, and
this report is what decides whether one is needed.

Finding the movements that *should* have an intent
--------------------------------------------------
Not by asking the movement whether it looks rail-ish — that question is what
made the first version of this report wrong, and wrong in the dangerous
direction. It asked FT's own ``mpesa_*`` columns, which were written on the
payout path only, so it measured the one subset that was covered by construction
and answered "100%, ready for cutover" on a database whose entire collection half
was missing.

The rail leg is discovered from the **ledger** instead, which no missing column
can hide: money crosses the external boundary only by moving through a settlement
account (``coa.MPESA_FLOAT``), so an FT whose journal touches one moved real
money. That catches collections and payouts alike, and correctly leaves out the
purely internal movements (ownership reallocation, surplus distribution) that
never touch the boundary.

Vocabulary
----------
*Settlement-backed*  the FT's journal touched a settlement account — money
                     actually crossed the external boundary. The denominator.
*Covered*            that FT has a linked ``PaymentIntent``. Post-cutover
                     readers find the rail dimension where they will look for it.
*Linkable*           no linked intent, but an unlinked intent correlates to it
                     (same receipt, or same provider ref). The backfill is a
                     link job — no data has to be invented.
*Missing*            rail evidence, but no intent exists anywhere. The backfill
                     has to mint one from the rail's own records. This is the
                     paybill (C2B) path, which never had an initiation to record.
*Unattributable*     money crossed the boundary but no rail correlation could be
                     found. Genuinely off-rail entries (a manual or cash
                     posting) look like this, and so does a payout still in
                     flight before dispatch. Needs a human, so it is never
                     silently counted as ready.
"""
from __future__ import annotations

from django.db.models import Q

from apps.ledger import coa

# Accounts money can only cross the external boundary through. An FT whose
# journal touches one of these moved real money in or out; anything else is an
# internal re-arrangement and correctly has no payment intent.
SETTLEMENT_ACCOUNT_CODES = (coa.MPESA_FLOAT,)

# Idempotency-key tails that are explicitly *not* a receipt. Collections build
# their key as ``<prefix>-<receipt>`` and fall back to one of these when the
# movement had no rail leg (see ContributionService.contribute).
_NON_RECEIPT_TAILS = frozenset({'', 'manual', 'none', 'null'})

# Shortest plausible provider receipt. An M-Pesa receipt is a ten-character
# alphanumeric code (e.g. ``SGH4KLM9N2``); the point of the check is only to
# tell a receipt apart from the row ids that other key shapes end in
# (``welfare-claim-42``), so it stays loose.
_MIN_RECEIPT_LEN = 6


def _looks_like_receipt(token: str) -> bool:
    """Whether an idempotency-key tail is plausibly a provider receipt.

    Deliberately a shape check, not a format rule: a receipt that fails it is
    classified ``unattributable``, which still withholds the cutover verdict —
    so being wrong here costs accuracy of advice, never safety.
    """
    return (len(token) >= _MIN_RECEIPT_LEN
            and token.lower() not in _NON_RECEIPT_TAILS
            and any(c.isalpha() for c in token)
            and any(c.isdigit() for c in token))

# Verdicts, in ascending order of "safe to proceed".
NEEDS_BACKFILL = 'needs_backfill'
NEEDS_REVIEW = 'needs_review'
READY = 'ready'
NO_DATA = 'no_data'


def settlement_backed_ft_ids():
    """FT ids whose journal touched a settlement account, as a subquery.

    Derived from the posted journal lines, so it reflects money that actually
    moved rather than a column a service happened to fill in. Returned as a
    queryset, not a materialised set, so the whole thing stays one server-side
    query however many movements the database holds.
    """
    from apps.ledger.models import JournalLine
    return (JournalLine.objects
            .filter(account__code__in=SETTLEMENT_ACCOUNT_CODES,
                    journal__financial_transaction__isnull=False)
            .values('journal__financial_transaction_id'))


def rail_backed_transactions():
    """Every FT that moved money over a rail, intents prefetched.

    Purely ledger-derived now. The old definition also unioned in FTs carrying
    legacy ``mpesa_*`` columns, so that a payout whose journal was missing could
    not slip out of the denominator; those columns are gone (ADR-0030), and the
    journal is the only evidence left — which is the evidence this report always
    argued was the right one.
    """
    from apps.ledger.models import FinancialTransaction
    return (FinancialTransaction.objects
            .filter(id__in=settlement_backed_ft_ids())
            .prefetch_related('payment_intents'))


def receipt_hint(ft) -> str:
    """The rail receipt recoverable from this FT, if any.

    FT stores no receipt of its own any more (ADR-0030), and
    ``create_fin_transaction`` never took rail parameters, so on an uncovered
    movement the receipt survives only inside the idempotency key the service
    built from it — ``contrib-stk-<receipt>``,
    ``contrib-<fund_id>-<receipt>``, ``welfare-contrib-<fund_id>-<user_id>-<receipt>``,
    ``shares-<fund_id>-<user_id>-<receipt>``, ``advance-repay-<advance_id>-<receipt>``.

    Reading it back out is a migration-time heuristic and is treated as one: it
    is used to *correlate* an existing intent, never to write anything. A tail
    that is a sentinel (``-manual``) or a bare row id (``welfare-claim-42``) is
    rejected, so an off-rail posting is not mistaken for a gap.
    """
    tail = (ft.idempotency_key or '').rsplit('-', 1)[-1]
    return tail if _looks_like_receipt(tail) else ''


def _unlinked_intent_index() -> dict[str, int]:
    """Intents with no FT of their own, indexed by receipt.

    These are the collection intents the STK chokepoint mints before its FT
    exists (``record_initiation`` is called with no ``financial_transaction``,
    and nothing ever fills it in). They are what makes most of the collection
    gap *linkable* rather than lost.
    """
    from apps.payments.models import PaymentIntent
    by_receipt: dict[str, int] = {}
    for pk, receipt in (PaymentIntent.objects
                        .filter(financial_transaction__isnull=True)
                        .exclude(receipt='')
                        .values_list('id', 'receipt')):
        by_receipt.setdefault(receipt, pk)
    return by_receipt


def _classify_uncovered(ft, by_receipt) -> tuple[str, int | None]:
    """Why this settlement-backed FT has no intent — and whether one can be found.

    Returns ``(bucket, linkable_intent_id)``.
    """
    receipt = receipt_hint(ft)
    if receipt and receipt in by_receipt:
        return 'linkable', by_receipt[receipt]
    if receipt:
        # Real rail evidence, but nothing to link it to — an intent has to be
        # minted from the rail's own records (the paybill case).
        return 'missing', None
    return 'unattributable', None


def _bump(counter: dict[str, int], key: str) -> None:
    counter[key] = counter.get(key, 0) + 1


def intent_coverage(*, sample: int = 20) -> dict:
    """Report PaymentIntent coverage over every FT that moved money over a rail.

    Returns counts plus a bounded sample of the problem rows, so the caller can
    decide whether a backfill is needed.
    """
    by_receipt = _unlinked_intent_index()

    total = covered = 0
    linkable = missing = unattributable = 0
    uncovered_by_op: dict[str, int] = {}
    uncovered_by_state: dict[str, int] = {}
    uncovered_by_bucket: dict[str, int] = {}
    uncovered_sample: list[dict] = []
    review_sample: list[dict] = []

    for ft in rail_backed_transactions().iterator(chunk_size=500):
        total += 1
        if ft.payment_intents.all():
            covered += 1
            continue

        bucket, intent_id = _classify_uncovered(ft, by_receipt)
        _bump(uncovered_by_bucket, bucket)
        if bucket == 'linkable':
            linkable += 1
        elif bucket == 'missing':
            missing += 1
        else:
            unattributable += 1

        _bump(uncovered_by_op, ft.op_type)
        _bump(uncovered_by_state, ft.state)

        row = {
            'ft_id': ft.id, 'op_type': ft.op_type, 'state': ft.state,
            'bucket': bucket,
            'receipt_hint': receipt_hint(ft),
            'linkable_intent_id': intent_id,
        }
        if bucket == 'unattributable':
            if len(review_sample) < sample:
                review_sample.append(row)
        elif len(uncovered_sample) < sample:
            uncovered_sample.append(row)

    uncovered = linkable + missing + unattributable
    # The backfillable gap: rail movements whose intent is absent or unlinked.
    # ``unattributable`` is deliberately excluded — it is a triage question, not
    # a backfill, and it gets its own verdict rather than being counted as ready.
    gap = linkable + missing
    pct = round(covered / total * 100, 2) if total else None

    if total == 0:
        verdict = NO_DATA
    elif gap:
        verdict = NEEDS_BACKFILL
    elif unattributable:
        verdict = NEEDS_REVIEW
    else:
        verdict = READY

    return {
        'total_rail_backed': total,
        'covered': covered,
        'uncovered': uncovered,
        'coverage_pct': pct,          # None when there is nothing to measure
        # The gap, split by what closing it actually takes.
        'linkable': linkable,         # backfill = set financial_transaction_id
        'missing': missing,           # backfill = mint an intent from rail records
        'unattributable': unattributable,   # triage: off-rail, or still in flight
        'gap': gap,
        'uncovered_by_op_type': uncovered_by_op,
        'uncovered_by_state': uncovered_by_state,
        'uncovered_by_bucket': uncovered_by_bucket,
        'uncovered_sample': uncovered_sample,
        'review_sample': review_sample,
        # No settlement-backed FTs at all means this database cannot answer the
        # question (an empty dev DB, or the wrong target) — deliberately NOT the
        # same as "ready", so an empty run can never green-light the cutover.
        'no_data': total == 0,
        'verdict': verdict,
        # Authoritative only when every rail movement has an intent and nothing
        # was left unexplained — and only when there was something to check.
        'ready_for_cutover': verdict == READY,
    }
