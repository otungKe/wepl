"""
Contribution Celery tasks.

execute_due_standing_orders — runs on schedule, fires only orders whose
    next_run_at has elapsed (fixes the "every order every run" bug).
"""
import logging

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
def notify_overdue_advances() -> int:
    """
    Find emergency advances whose repayment_due date has passed and whose
    borrower has not yet fully repaid, then send a reminder notification.

    Runs daily via Celery Beat.
    Sends at most one notification per advance per day (idempotency via
    a simple date check on the advance's last_notified_at field — or, since
    we don't track that, we simply re-notify every day until repaid).

    Returns the number of overdue advances found.
    """
    from datetime import timedelta
    from apps.contributions.models import EmergencyAdvance
    from apps.contributions.services import _notify

    today = timezone.now().date()
    overdue = EmergencyAdvance.objects.filter(
        status__in=['APPROVED', 'DISBURSED'],
        repayment_due__lt=today,
    ).select_related('borrower', 'contribution')

    count = 0
    for advance in overdue:
        days_late = (today - advance.repayment_due).days
        _notify(
            user=advance.borrower,
            notification_type='advance_requested',   # reuses the advance icon
            title="Advance repayment overdue",
            message=(
                f"Your KES {advance.amount:,.0f} advance from "
                f"'{advance.contribution.title}' was due "
                f"{advance.repayment_due.strftime('%d %b %Y')} "
                f"({days_late} day{'s' if days_late != 1 else ''} ago). "
                f"Outstanding: KES {advance.balance_due:,.0f}."
            ),
            contribution_id=advance.contribution_id,
            join_request_id=advance.id,
        )
        count += 1
        logger.warning(
            "Overdue advance %s: borrower %s, due %s, days_late=%d, balance=%.2f",
            advance.id, advance.borrower.phone_number,
            advance.repayment_due, days_late, advance.balance_due,
        )

    if count:
        logger.warning("notify_overdue_advances: %d overdue advance(s) notified.", count)
    else:
        logger.info("notify_overdue_advances: no overdue advances.")
    return count
