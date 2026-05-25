"""
Contribution Celery tasks.

execute_due_standing_orders — runs on schedule, fires only orders whose
    next_run_at has elapsed (fixes the "every order every run" bug).

reconcile_balances — compares ledger-derived balances against the legacy
    mutable balance fields for Contributions, WelfareFunds, and SharesFunds.
    A mismatch indicates a real dual-write bug and requires human review.
"""
import logging
from decimal import Decimal

from celery import shared_task
from django.core.exceptions import ValidationError
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(queue='financial')
def execute_due_standing_orders() -> int:
    """
    Find active standing orders whose next_run_at ≤ now and execute them.

    Uses select_for_update(skip_locked=True) so concurrent Celery workers
    skip orders another worker is already processing — no double-execution.

    Each execution dispatches a B2C Celery task and advances next_run_at
    to prevent re-triggering until the next cycle.
    """
    from .models import StandingOrder
    from .services import StandingOrderService

    now = timezone.now()
    orders = StandingOrder.objects.select_for_update(skip_locked=True).filter(
        is_active=True,
        next_run_at__lte=now,
    ).select_related('contribution', 'created_by')

    executed = 0
    for order in orders:
        try:
            StandingOrderService.execute_standing_order(order.id, order.created_by)
            executed += 1
            logger.info(
                "execute_due_standing_orders: order %s executed (KES %s → %s)",
                order.id, order.amount,
                order.fixed_payee_phone or "rotating-slot",
            )
        except ValidationError as e:
            # Insufficient funds, inactive order, no next slot — expected, log and skip
            logger.warning(
                "execute_due_standing_orders: order %s skipped — %s", order.id, e
            )
        except Exception as e:
            logger.error(
                "execute_due_standing_orders: order %s failed — %s", order.id, e,
                exc_info=True,
            )

    logger.info("execute_due_standing_orders: executed %d order(s)", executed)
    return executed


@shared_task(queue='financial')
def reconcile_balances() -> int:
    """
    Sanity check: compare ledger-derived balances against the legacy mutable
    balance fields for all three fund types.

    Fund type        | Legacy field            | Ledger query
    -----------------+-------------------------+-------------------------
    Contribution     | current_amount          | contribution_balance()
    WelfareFund      | balance                 | welfare_fund_balance()
    SharesFund       | total_pool              | shares_fund_balance()

    Does NOT auto-correct — human review required for any drift detected.
    Returns the total number of discrepancies found across all fund types.
    """
    from .models import Contribution, WelfareFund, SharesFund
    from apps.ledger.queries import (
        contribution_balance,
        welfare_fund_balance,
        shares_fund_balance,
    )

    DRIFT_THRESHOLD = Decimal('0.01')
    discrepancies = []

    # ── Contributions ─────────────────────────────────────────────────────────
    for contrib in Contribution.objects.filter(is_active=True):
        ledger_bal = contribution_balance(contrib.id)
        stored_bal = contrib.current_amount
        drift      = abs(ledger_bal - stored_bal)

        if drift > DRIFT_THRESHOLD:
            discrepancies.append({
                'type':   'contribution',
                'id':     contrib.id,
                'label':  contrib.title,
                'stored': str(stored_bal),
                'ledger': str(ledger_bal),
                'drift':  str(drift),
            })
            logger.warning(
                "Balance drift [contribution %s '%s']: stored=%s ledger=%s drift=%s",
                contrib.id, contrib.title, stored_bal, ledger_bal, drift,
            )

    # ── Welfare Funds ─────────────────────────────────────────────────────────
    for fund in WelfareFund.objects.select_related('community').all():
        ledger_bal = welfare_fund_balance(fund.id)
        stored_bal = fund.balance
        drift      = abs(ledger_bal - stored_bal)

        if drift > DRIFT_THRESHOLD:
            label = fund.community.name if fund.community else f"fund-{fund.id}"
            discrepancies.append({
                'type':   'welfare_fund',
                'id':     fund.id,
                'label':  label,
                'stored': str(stored_bal),
                'ledger': str(ledger_bal),
                'drift':  str(drift),
            })
            logger.warning(
                "Balance drift [welfare_fund %s '%s']: stored=%s ledger=%s drift=%s",
                fund.id, label, stored_bal, ledger_bal, drift,
            )

    # ── Shares Funds ──────────────────────────────────────────────────────────
    for fund in SharesFund.objects.select_related('community').all():
        ledger_bal = shares_fund_balance(fund.id)
        stored_bal = fund.total_pool
        drift      = abs(ledger_bal - stored_bal)

        if drift > DRIFT_THRESHOLD:
            label = fund.community.name if fund.community else f"fund-{fund.id}"
            discrepancies.append({
                'type':   'shares_fund',
                'id':     fund.id,
                'label':  label,
                'stored': str(stored_bal),
                'ledger': str(ledger_bal),
                'drift':  str(drift),
            })
            logger.warning(
                "Balance drift [shares_fund %s '%s']: stored=%s ledger=%s drift=%s",
                fund.id, label, stored_bal, ledger_bal, drift,
            )

    # ── Summary ───────────────────────────────────────────────────────────────
    if discrepancies:
        logger.error(
            "reconcile_balances: %d discrepancy(ies) found: %s",
            len(discrepancies), discrepancies,
        )
    else:
        logger.info("reconcile_balances: all balances match across all fund types.")

    return len(discrepancies)
