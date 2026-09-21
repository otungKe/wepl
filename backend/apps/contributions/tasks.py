"""
Contribution Celery tasks.

execute_due_standing_orders — runs on schedule, fires only orders whose
    next_run_at has elapsed, claiming each one under its own row lock.
"""
import logging

from celery import shared_task
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(queue='financial')
def execute_due_standing_orders() -> int:
    """
    Find active standing orders whose next_run_at <= now and execute them.

    Each order is claimed and executed in its OWN transaction:

      * ``select_for_update`` requires a transaction — evaluating the locking
        queryset at task level raised ``TransactionManagementError`` on every
        run, so this task had never executed an order.
      * ``skip_locked`` lets a second worker move past an order another worker
        is mid-way through instead of blocking behind it.
      * The due predicate is re-checked *inside* the lock. A worker that waited
        for the lock (or listed the order before a sibling finished it) would
        otherwise re-run an order whose ``next_run_at`` has just advanced — and
        because the idempotency key is anchored to ``next_run_at``, the replay
        would mint a *new* key and pay out twice.
      * One transaction per order keeps the row locks short and keeps
        ``execute_standing_order``'s ``on_commit`` B2C dispatch tied to that
        order's own commit rather than to the end of the whole batch.
    """
    from .models import StandingOrder
    from .services import StandingOrderService

    now = timezone.now()
    due_ids = list(
        StandingOrder.objects
        .filter(is_active=True, next_run_at__lte=now)
        .order_by('next_run_at', 'id')
        .values_list('id', flat=True)
    )

    executed = 0
    for order_id in due_ids:
        try:
            with transaction.atomic():
                order = (
                    StandingOrder.objects
                    .select_for_update(skip_locked=True)
                    .filter(id=order_id, is_active=True, next_run_at__lte=now)
                    .select_related('contribution', 'created_by')
                    .first()
                )
                if order is None:
                    # Locked by another worker, or no longer due — someone else
                    # has it, or has already run it.
                    continue
                StandingOrderService.execute_standing_order(order.id, order.created_by)
        except ValidationError as e:
            # Insufficient funds, inactive order, no next slot — expected, log and skip
            logger.warning(
                "execute_due_standing_orders: order %s skipped — %s", order_id, e
            )
            continue
        except Exception as e:
            logger.error(
                "execute_due_standing_orders: order %s failed — %s", order_id, e,
                exc_info=True,
            )
            continue

        executed += 1
        logger.info(
            "execute_due_standing_orders: order %s executed (KES %s → %s)",
            order.id, order.amount,
            order.fixed_payee_phone or "rotating-slot",
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
