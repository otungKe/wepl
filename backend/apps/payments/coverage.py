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

Finding the movements that *should* have an intent
--------------------------------------------------
The obvious test — "does this FT carry a ``mpesa_*`` column?" — is wrong, and
wrong in the dangerous direction. Those columns are written **only on the payout
path** (``apps/ledger/tasks.py`` stamps ``mpesa_conversation_id``, the B2C callback
stamps ``mpesa_receipt``); ``create_fin_transaction`` takes no rail arguments at
all, so *every* collection FT — contributions, welfare, shares, advance
repayments, STK and paybill alike — has all three NULL. Payouts are also the only
path that links its intent to its FT. Asking FT's columns therefore measures the
one subset that is covered by construction, and reports "100%, ready for cutover"
on a database where the entire collection side is missing.

So the rail leg is discovered from the **ledger** instead, which cannot be
sidestepped by a column nobody writes: money crosses the external boundary only
by moving through a settlement account (``coa.MPESA_FLOAT``), so an FT whose
journal touches one moved real money. That catches collections and payouts alike,
and correctly leaves out the purely internal movements (ownership reallocation,
surplus distribution) that never touch the boundary.

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
*Mismatched*         covered, but the intent's ``provider_ref``/``receipt``
                     disagrees with the FT's columns — coverage without
                     agreement, which would silently change reads at cutover.
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

# FTs still carrying rail evidence in their own columns. This is no longer how
# the rail leg is *found*, but it is exactly the set whose data would be lost if
# Slice A dropped the columns — so it is still measured, separately.
_LEGACY_RAIL_COLUMNS = (
    ~Q(mpesa_conversation_id__isnull=True) & ~Q(mpesa_conversation_id='')
    | ~Q(mpesa_checkout_id__isnull=True) & ~Q(mpesa_checkout_id='')
    | ~Q(mpesa_receipt__isnull=True) & ~Q(mpesa_receipt='')
)

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

    The union of the ledger-derived settlement set and the FTs still carrying
    legacy rail columns — the latter so a payout whose journal is missing (the
    very drift this report exists to surface) cannot slip out of the denominator.
    """
    from apps.ledger.models import FinancialTransaction
    return (FinancialTransaction.objects
            .filter(Q(id__in=settlement_backed_ft_ids()) | _LEGACY_RAIL_COLUMNS)
            .prefetch_related('payment_intents'))


def receipt_hint(ft) -> str:
    """The rail receipt recorded against this FT, if any.

    Payouts carry it in a column. Collections do not: ``create_fin_transaction``
    has no rail parameters, so the receipt survives only inside the idempotency
    key the service built from it — ``contrib-stk-<receipt>``,
    ``contrib-<fund_id>-<receipt>``, ``welfare-contrib-<fund_id>-<user_id>-<receipt>``,
    ``shares-<fund_id>-<user_id>-<receipt>``, ``advance-repay-<advance_id>-<receipt>``.

    Reading it back out is a migration-time heuristic and is treated as one: it
    is used to *correlate* an existing intent, never to write anything. A tail
    that is a sentinel (``-manual``) or a bare row id (``welfare-claim-42``) is
    rejected, so an off-rail posting is not mistaken for a gap.
    """
    if ft.mpesa_receipt:
        return ft.mpesa_receipt
    tail = (ft.idempotency_key or '').rsplit('-', 1)[-1]
    return tail if _looks_like_receipt(tail) else ''


def _unlinked_intent_index() -> tuple[dict[str, int], dict[str, int]]:
    """Intents with no FT of their own, indexed by receipt and by provider ref.

    These are the collection intents the STK chokepoint mints before its FT
    exists (``record_initiation`` is called with no ``financial_transaction``,
    and nothing ever fills it in). They are what makes most of the collection
    gap *linkable* rather than lost.
    """
    from apps.payments.models import PaymentIntent
    by_receipt: dict[str, int] = {}
    by_ref: dict[str, int] = {}
    for pk, receipt, ref in (PaymentIntent.objects
                             .filter(financial_transaction__isnull=True)
                             .values_list('id', 'receipt', 'provider_ref')):
        if receipt:
            by_receipt.setdefault(receipt, pk)
        if ref:
            by_ref.setdefault(ref, pk)
    return by_receipt, by_ref


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


def _classify_uncovered(ft, by_receipt, by_ref) -> tuple[str, int | None]:
    """Why this settlement-backed FT has no intent — and whether one can be found.

    Returns ``(bucket, linkable_intent_id)``.
    """
    ref = ft.mpesa_conversation_id or ft.mpesa_checkout_id or ''
    if ref and ref in by_ref:
        return 'linkable', by_ref[ref]

    receipt = receipt_hint(ft)
    if receipt and receipt in by_receipt:
        return 'linkable', by_receipt[receipt]
    if receipt or ref:
        # Real rail evidence, but nothing to link it to — an intent has to be
        # minted from the rail's own records (the paybill case).
        return 'missing', None
    return 'unattributable', None


def _bump(counter: dict[str, int], key: str) -> None:
    counter[key] = counter.get(key, 0) + 1


def intent_coverage(*, sample: int = 20) -> dict:
    """Report PaymentIntent coverage over every FT that moved money over a rail.

    Returns counts plus a bounded sample of the problem rows, so the caller can
    decide whether a backfill is needed before the Slice A cutover.
    """
    by_receipt, by_ref = _unlinked_intent_index()

    total = covered = mismatched = 0
    linkable = missing = unattributable = 0
    legacy_rail = legacy_at_risk = 0
    uncovered_by_op: dict[str, int] = {}
    uncovered_by_state: dict[str, int] = {}
    uncovered_by_bucket: dict[str, int] = {}
    uncovered_sample: list[dict] = []
    mismatch_sample: list[dict] = []
    review_sample: list[dict] = []

    for ft in rail_backed_transactions().iterator(chunk_size=500):
        total += 1
        intents = list(ft.payment_intents.all())
        has_legacy = bool(ft.mpesa_conversation_id or ft.mpesa_checkout_id
                          or ft.mpesa_receipt)
        if has_legacy:
            legacy_rail += 1

        if intents:
            covered += 1
            problems = _mismatches(ft, intents)
            if problems:
                mismatched += 1
                if has_legacy:
                    legacy_at_risk += 1
                if len(mismatch_sample) < sample:
                    mismatch_sample.append({'ft_id': ft.id, 'problems': problems})
            continue

        if has_legacy:
            # Rail data living only on FT, with no intent to carry it forward:
            # dropping the columns in Slice A would lose it outright.
            legacy_at_risk += 1

        bucket, intent_id = _classify_uncovered(ft, by_receipt, by_ref)
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
            'conversation_id': ft.mpesa_conversation_id or '',
            'checkout_id': ft.mpesa_checkout_id or '',
            'receipt': ft.mpesa_receipt or '',
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
    elif gap or mismatched:
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
        'mismatched': mismatched,
        # The gap, split by what closing it actually takes.
        'linkable': linkable,         # backfill = set financial_transaction_id
        'missing': missing,           # backfill = mint an intent from rail records
        'unattributable': unattributable,   # triage: off-rail, or still in flight
        'gap': gap,
        # The Slice A column-drop question: rail data that today lives only on
        # FT, and would be lost outright if the columns went away.
        'legacy_rail_columns': legacy_rail,
        'legacy_at_risk': legacy_at_risk,
        'uncovered_by_op_type': uncovered_by_op,
        'uncovered_by_state': uncovered_by_state,
        'uncovered_by_bucket': uncovered_by_bucket,
        'uncovered_sample': uncovered_sample,
        'mismatch_sample': mismatch_sample,
        'review_sample': review_sample,
        # No settlement-backed FTs at all means this database cannot answer the
        # question (an empty dev DB, or the wrong target) — deliberately NOT the
        # same as "ready", so an empty run can never green-light the cutover.
        'no_data': total == 0,
        'verdict': verdict,
        # Authoritative only when every rail movement has an agreeing intent,
        # and nothing was left unexplained — and only when there was something
        # to check.
        'ready_for_cutover': verdict == READY,
    }
