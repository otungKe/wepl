"""
Ops alerting — OP-2.

``ops_alerts`` runs on a short schedule and evaluates the system-health
conditions that matter for a money operation. On breach it emits a Sentry event
and raises a ``StaffNotice`` (the console bell); when a condition clears it
auto-resolves its notice. De-duplicated by condition ``key`` so a persistent
breach is one notice, not one per run.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)

# Conditions this task owns — so it can resolve a notice when the breach clears.
MANAGED_KEYS = {
    "ledger_unbalanced", "outbox_dead", "outbox_backlog",
    "stuck_payouts", "worker_stale",
}

OUTBOX_BACKLOG_SECONDS = 600     # oldest pending outbox event
STUCK_PAYOUT_MINUTES = 30


def _sentry(message: str, level: str, extra: dict) -> None:
    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            for k, v in extra.items():
                scope.set_extra(k, v)
            sentry_sdk.capture_message(message, level=("error" if level == "CRITICAL" else "warning"))
    except Exception:
        pass


def _evaluate() -> dict[str, tuple[str, str, str]]:
    """Return {key: (level, title, message)} for every breached condition."""
    from decimal import Decimal

    from apps.core.health import queue_depths, stale_tasks   # noqa: F401 (queue_depths reserved)
    from apps.core.models import OutboxEvent
    from apps.ledger.balances import trial_balance
    from apps.ledger.models import FinancialTransaction as FT
    from apps.payments.ops import PAYOUT_OP_TYPES

    breaches: dict[str, tuple[str, str, str]] = {}

    # Ledger must balance — anything else is a money incident.
    tb = trial_balance()
    debit = tb.get("total_debit") or Decimal("0")
    credit = tb.get("total_credit") or Decimal("0")
    if not tb.get("balanced", debit == credit):
        breaches["ledger_unbalanced"] = (
            "CRITICAL", "Ledger out of balance",
            f"Trial balance delta is {debit - credit}. The books must sum to zero.")

    # Dead-lettered domain events — a member action that never took effect.
    dead = OutboxEvent.objects.filter(status=OutboxEvent.Status.DEAD).count()
    if dead:
        breaches["outbox_dead"] = (
            "CRITICAL", f"{dead} dead-lettered event(s)",
            "Domain events failed every retry. Inspect and requeue in System Health.")

    # Outbox backlog — the relay is behind (or stopped).
    oldest = (OutboxEvent.objects.filter(status=OutboxEvent.Status.PENDING)
              .order_by("created_at").values_list("created_at", flat=True).first())
    if oldest:
        age = (timezone.now() - oldest).total_seconds()
        if age > OUTBOX_BACKLOG_SECONDS:
            breaches["outbox_backlog"] = (
                "WARNING", "Outbox backlog building",
                f"Oldest pending event is {round(age / 60)} min old — the relay may be stalled.")

    # Stuck payouts — money going out that stalled.
    cutoff = timezone.now() - timedelta(minutes=STUCK_PAYOUT_MINUTES)
    stuck = FT.objects.filter(
        op_type__in=PAYOUT_OP_TYPES,
        state__in=(FT.State.PENDING, FT.State.PROCESSING),
        created_at__lte=cutoff).count()
    if stuck:
        breaches["stuck_payouts"] = (
            "WARNING", f"{stuck} stuck payout(s)",
            f"Payouts open > {STUCK_PAYOUT_MINUTES} min. Recover them on the FinOps desk.")

    # A watched worker went quiet.
    stale = stale_tasks()
    if stale:
        breaches["worker_stale"] = (
            "WARNING", "Worker heartbeat stale",
            "No recent heartbeat from: " + ", ".join(t.split(".")[-1] for t in stale))

    return breaches


@shared_task(name="apps.backoffice.tasks.ops_alerts")
def ops_alerts() -> dict:
    from .models import StaffNotice

    breaches = _evaluate()
    raised, resolved = 0, 0

    for key, (level, title, message) in breaches.items():
        exists = StaffNotice.objects.filter(
            key=key, resolved_at__isnull=True, dismissed_at__isnull=True).exists()
        if not exists:
            StaffNotice.objects.create(key=key, level=level, title=title, message=message)
            _sentry(title, level, {"key": key, "message": message})
            raised += 1

    # Auto-resolve open notices whose condition has cleared.
    cleared = MANAGED_KEYS - set(breaches)
    if cleared:
        resolved = StaffNotice.objects.filter(
            key__in=cleared, resolved_at__isnull=True, dismissed_at__isnull=True
        ).update(resolved_at=timezone.now())

    if raised or resolved:
        logger.info("ops_alerts: raised=%d resolved=%d breaches=%s",
                    raised, resolved, sorted(breaches))
    return {"raised": raised, "resolved": resolved, "breaches": sorted(breaches)}
