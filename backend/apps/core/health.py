"""
System-health primitives — OP-2.

Worker heartbeats (is the async nervous system alive?) and Celery queue depths.
Heartbeats are DB-backed (``WorkerHeartbeat``): each watched beat task stamps
``last_seen`` on completion via a ``task_postrun`` signal (see
``CoreConfig.ready``). Queue depths are read best-effort from the Redis broker.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

# Watched beat tasks → max seconds between runs before the worker is "stale".
# Windows are the schedule interval plus generous grace; only the frequent
# "nervous-system" tasks are watched (sparse daily jobs would false-positive).
WATCHED_TASKS: dict[str, int] = {
    "apps.core.tasks.process_outbox": 180,                              # every 10s
    "apps.ledger.tasks.recover_stale_processing_transactions": 2700,   # every 30m
    "apps.payments.tasks.reconcile_payments": 5400,                    # hourly
    "apps.reminders.tasks.fire_due_reminders": 2700,                   # every 30m
}

CELERY_QUEUES = ["default", "notifications", "payments", "financial"]


def stamp(task_name: str) -> None:
    """Record that a beat task just completed."""
    from .models import WorkerHeartbeat
    WorkerHeartbeat.objects.update_or_create(
        task_name=task_name, defaults={"last_seen": timezone.now()})


def heartbeats() -> list[dict]:
    """One row per watched task: last_seen, age, and whether it has gone stale.

    ``stale`` means we saw the task before and it has since gone quiet (a real
    regression). A task never seen yet is ``never_seen`` — surfaced but not
    treated as stale, so a fresh boot before the first run doesn't false-alarm.
    """
    from .models import WorkerHeartbeat
    seen = {h.task_name: h.last_seen for h in WorkerHeartbeat.objects.all()}
    now = timezone.now()
    rows = []
    for task, window in WATCHED_TASKS.items():
        last = seen.get(task)
        age = round((now - last).total_seconds()) if last else None
        rows.append({
            "task": task,
            "last_seen": last.isoformat() if last else None,
            "age_seconds": age,
            "window_seconds": window,
            "stale": bool(last and age > window),
            "never_seen": last is None,
        })
    return rows


def stale_tasks() -> list[str]:
    return [h["task"] for h in heartbeats() if h["stale"]]


def queue_depths() -> dict[str, int | None]:
    """Best-effort Celery queue depths (Redis ``llen``). None per queue if the
    broker is unreachable — health reads must never fail on infra."""
    try:
        import redis
        client = redis.from_url(settings.CELERY_BROKER_URL)
        return {q: client.llen(q) for q in CELERY_QUEUES}
    except Exception:
        logger.warning("queue_depths: broker unreachable", exc_info=True)
        return {q: None for q in CELERY_QUEUES}
