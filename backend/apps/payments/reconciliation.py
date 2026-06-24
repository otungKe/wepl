"""Payments reconciliation (ADR-0014).

A periodic pass that cross-checks the three views of money movement and records
any disagreement as a ReconciliationDrift for ops triage:

  * PaymentIntent (the external provider attempt)
  * FinancialTransaction (the internal money-op)
  * the double-entry ledger (the posted journal)

A true provider-statement leg (fetching the rail's settlement file) needs the
Daraja transaction-query API and is a documented follow-up; this pass covers the
intent↔FT↔ledger legs over live data and flags stuck/mismatched records.
"""
import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

# How long a record may sit unresolved before it's considered drift.
PENDING_INTENT_MAX_AGE  = timedelta(hours=2)
FT_PROCESSING_MAX_AGE   = timedelta(hours=2)


def _open_drift(kind, subject_type, subject_id, detail):
    from .models import ReconciliationDrift
    _, created = ReconciliationDrift.objects.get_or_create(
        kind=kind, subject_type=subject_type, subject_id=str(subject_id),
        resolved_at__isnull=True,
        defaults={'detail': detail[:2000]},
    )
    if created:
        logger.warning("Reconciliation drift [%s] %s#%s: %s",
                       kind, subject_type, subject_id, detail)
    return created


def reconcile_payments() -> dict:
    """Run all reconciliation checks. Returns a per-kind drift count (new opens)."""
    from .models import PaymentIntent
    from apps.ledger.models import FinancialTransaction, JournalEntry

    now = timezone.now()
    counts = {}

    def bump(kind, n=1):
        counts[kind] = counts.get(kind, 0) + n

    # 1) Intents stuck PENDING past the grace window.
    stuck = PaymentIntent.objects.filter(
        status=PaymentIntent.Status.PENDING,
        created_at__lt=now - PENDING_INTENT_MAX_AGE,
    )
    for intent in stuck.iterator():
        if _open_drift('stuck_pending_intent', 'payment_intent', intent.id,
                       f"{intent.provider}/{intent.direction} ref={intent.provider_ref} "
                       f"pending since {intent.created_at:%Y-%m-%d %H:%M}"):
            bump('stuck_pending_intent')

    # 2) Intent ↔ FT state mismatch (where the intent is linked to an FT).
    linked = PaymentIntent.objects.exclude(financial_transaction=None).select_related(
        'financial_transaction')
    for intent in linked.iterator():
        ft = intent.financial_transaction
        succeeded = intent.status == PaymentIntent.Status.SUCCEEDED
        ft_success = ft.state == FinancialTransaction.State.SUCCESS
        # Only flag terminal disagreement (ignore both-still-in-flight).
        if succeeded != ft_success and intent.status in (
            PaymentIntent.Status.SUCCEEDED, PaymentIntent.Status.FAILED
        ) and ft.state in (
            FinancialTransaction.State.SUCCESS, FinancialTransaction.State.FAILED
        ):
            if _open_drift('intent_ft_mismatch', 'payment_intent', intent.id,
                           f"intent={intent.status} but FT {ft.id}={ft.state}"):
                bump('intent_ft_mismatch')

    # 3) Successful FT without a posted journal entry (ledger linkage broken).
    success_fts = FinancialTransaction.objects.filter(
        state=FinancialTransaction.State.SUCCESS)
    posted_ft_ids = set(
        JournalEntry.objects.filter(financial_transaction__in=success_fts)
        .values_list('financial_transaction_id', flat=True)
    )
    for ft in success_fts.exclude(id__in=posted_ft_ids).iterator():
        if _open_drift('ft_without_journal', 'financial_transaction', ft.id,
                       f"FT {ft.id} ({ft.op_type}) is SUCCESS but has no journal entry"):
            bump('ft_without_journal')

    # 4) FT stuck in PROCESSING past the grace window.
    stuck_ft = FinancialTransaction.objects.filter(
        state=FinancialTransaction.State.PROCESSING,
        updated_at__lt=now - FT_PROCESSING_MAX_AGE,
    )
    for ft in stuck_ft.iterator():
        if _open_drift('ft_stuck_processing', 'financial_transaction', ft.id,
                       f"FT {ft.id} ({ft.op_type}) in PROCESSING since {ft.updated_at:%Y-%m-%d %H:%M}"):
            bump('ft_stuck_processing')

    logger.info("reconcile_payments: opened drifts %s", counts or "{}")
    return counts
