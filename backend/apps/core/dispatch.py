"""Resilient dispatch of best-effort side effects — Celery enqueues and Channels
broadcasts — so a broker/Channels (Redis) outage degrades gracefully instead of
500-ing a request whose primary work (the DB write) already succeeded.

Same posture as the fail-open throttles (apps.core.throttling): a transient
infrastructure blip must not cascade into a user-visible error or, worse, an
inconsistent write. The domain state is already committed; the async follow-up
is retried or swept up later.

- ``safe_enqueue`` — fire a Celery task, swallowing broker errors. Pass
  ``critical=True`` for money-path dispatch so the (rare) failure logs at CRITICAL
  and is caught by the stuck-transaction sweep / ops retry lever, not lost.
- ``safe_group_send`` — broadcast to a Channels group best-effort; a Channels
  outage never fails a REST write (clients reconcile on their next fetch).
"""
import logging

logger = logging.getLogger(__name__)


def safe_enqueue(task, *args, critical: bool = False, options: dict | None = None,
                 **kwargs) -> bool:
    """Enqueue ``task`` with ``args``/``kwargs``; never raise on a broker outage.

    ``options`` carries ``apply_async`` routing options (e.g. ``{"queue": "payments"}``).
    Returns True if the task was accepted by the broker, False otherwise. A False
    for a money-path dispatch (``critical=True``) is logged at CRITICAL so the
    stranded work is visible; the FinancialTransaction is already committed and is
    recoverable via the stuck-payout alert + ops retry lever.
    """
    try:
        task.apply_async(args=args, kwargs=kwargs, **(options or {}))
        return True
    except Exception:
        logger.log(
            logging.CRITICAL if critical else logging.WARNING,
            "safe_enqueue: broker unavailable — task %s not queued (critical=%s). "
            "Domain state is committed; recover via sweep/retry.",
            getattr(task, "name", task), critical, exc_info=True,
        )
        return False


def safe_group_send(group: str, payload: dict) -> bool:
    """Broadcast ``payload`` to a Channels ``group`` best-effort.

    Returns True on success, False if the channel layer is unavailable. Never
    raises — a live-broadcast failure must not 500 a REST write that already
    persisted; connected clients reconcile via their next REST fetch.
    """
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        layer = get_channel_layer()
        if layer is None:
            return False
        async_to_sync(layer.group_send)(group, payload)
        return True
    except Exception:
        logger.warning(
            "safe_group_send: channel layer unavailable — broadcast to %s dropped; "
            "clients will reconcile on next fetch.", group, exc_info=True,
        )
        return False
