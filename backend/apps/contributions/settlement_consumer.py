"""Inline settlement consumer (ADR-0028 propagation, ADR-0029 Stage 2).

The single *propagation* path for a settled/failed payout: reverse-or-confirm the
ledger, advance the linked domain object, and notify. Discovery stays multi-source
(callback + requery sweep + operator) and each witness emits one durable
``payment.settled`` / ``payment.failed`` event (ADR-0028); this consumer runs the
propagation exactly once per delivery, independently of the notification lane.

Registered as an ``inline_atomic`` consumer, so ``process_inline_deliveries`` runs
``handle_settlement`` inside the transaction that acks the delivery row. It must be
idempotent — at-least-once delivery, plus multi-source discovery, means the same
settlement can be delivered more than once. It is: ``on_payout_settled`` /
``on_payout_failed`` tolerate re-application (see apps/contributions/settlement.py)
and ``reverse_financial_transaction`` is a no-op once the FT is already reversed.

Dormant until a discovery site emits these events (the cutover is a later slice);
until then no ``payment.settled`` / ``payment.failed`` event is produced, so this
consumer receives nothing.
"""
import logging

logger = logging.getLogger(__name__)

CONSUMER_NAME = "contributions.settlement"
SETTLED = "payment.settled"
FAILED = "payment.failed"


def handle_settlement(event) -> None:
    """Propagate one settlement fact. ``event.payload`` carries ``ft_id`` plus
    ``receipt`` (settled) or ``reason`` (failed)."""
    from apps.ledger.models import FinancialTransaction
    from apps.ledger.posting import reverse_financial_transaction

    from .settlement import on_payout_failed, on_payout_settled

    body = event.payload or {}
    ft_id = body.get("ft_id")
    if ft_id is None:
        raise ValueError(f"settlement event {event.id} missing ft_id")

    ft = FinancialTransaction.objects.get(id=ft_id)

    if event.event_type == SETTLED:
        # Funds already moved at reserve time; confirm = advance domain + notify.
        on_payout_settled(ft, body.get("receipt", ""))
    elif event.event_type == FAILED:
        # Restore the reservation (idempotent), then reset the domain object.
        reverse_financial_transaction(ft, note=(body.get("reason") or "")[:500])
        on_payout_failed(ft)
    else:  # pragma: no cover - registry only routes the two types here
        raise ValueError(
            f"settlement consumer received unexpected event_type {event.event_type!r}")


def register() -> None:
    """Register the consumer with Core's inline lane (called from AppConfig.ready)."""
    from apps.core.events import register_inline_consumer

    register_inline_consumer(CONSUMER_NAME, {SETTLED, FAILED}, handle_settlement)
