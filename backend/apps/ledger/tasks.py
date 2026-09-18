"""
Ledger Celery tasks — integrity of the book of record.

The ledger depends on nothing above it and knows nothing of a payment rail
(Module-Boundaries Rule 1 / P-18). Payout *orchestration* — dispatching a B2C
payment, polling the rail for a stalled one, finalising a failure — moved to
``apps/payments/payouts.py`` in #159; what is left here is book-keeping that
reads only the ledger's own tables.
"""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Reconciliation & observability (P0-08)
# ═══════════════════════════════════════════════════════════════════════════

def _alert(message: str, extra: dict) -> None:
    """Send a Sentry alert if configured; always safe to call."""
    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            for k, v in extra.items():
                scope.set_extra(k, v)
            sentry_sdk.capture_message(message, level="error")
    except Exception:  # sentry not installed/configured — logging already covers it
        pass


@shared_task(queue='financial')
def reconcile_ledger(repair: bool = True) -> dict:
    """Nightly ledger-integrity check (the safety net for the authoritative core).

    1. Global trial balance must be zero (Σdebit == Σcredit across all lines).
    2. Every account's AccountBalance projection must equal a replay of its
       immutable lines; drifted projections are auto-repaired when ``repair`` is
       True and always reported.

    Any imbalance or drift is logged and raised to Sentry via _alert(). Returns a
    summary dict.
    """
    from .balances import reconcile_account, recompute_account_balance, trial_balance
    from .models import Account

    tb = trial_balance()
    drifted: list[dict] = []
    for account in Account.objects.all().iterator():
        result = reconcile_account(account)
        if not result['ok']:
            drifted.append(result)
            if repair:
                recompute_account_balance(account)

    report = {
        'balanced':     tb['balanced'],
        'total_debit':  str(tb['total_debit']),
        'total_credit': str(tb['total_credit']),
        'drift_count':  len(drifted),
        'repaired':     repair,
    }

    if not tb['balanced']:
        logger.critical(
            "LEDGER IMBALANCE: trial balance debit=%s credit=%s",
            tb['total_debit'], tb['total_credit'],
        )
        _alert("Ledger trial balance is not zero", report)

    if drifted:
        codes = [d['account'] for d in drifted]
        logger.error(
            "Ledger projection drift on %d account(s)%s: %s",
            len(drifted), " (auto-repaired)" if repair else "", codes[:20],
        )
        _alert(f"Ledger projection drift on {len(drifted)} account(s)",
               {**report, 'accounts': codes[:50]})

    if tb['balanced'] and not drifted:
        logger.info("reconcile_ledger: OK — trial balance zero, all projections match.")

    return report
