"""Held/denied movement review queue (P3-04).

A control exception (LimitExceeded / ControlHeld) propagates out of the money
service's ``@transaction.atomic`` block, rolling back the FinancialTransaction.
The DRF exception handler then calls ``record_blocked_movement`` — which runs
*outside* that rolled-back transaction — to durably persist the blocked movement
for manual review.
"""
import logging
from decimal import Decimal

from .models import HeldMovement

logger = logging.getLogger(__name__)


def record_blocked_movement(exc) -> HeldMovement | None:
    """Persist a blocked movement to the review queue from an exception's context."""
    ctx = getattr(exc, 'context', None)
    if not ctx:
        return None
    return HeldMovement.objects.create(
        decision=ctx.get('decision', HeldMovement.Decision.HOLD),
        op_type=ctx.get('op_type', ''),
        direction=ctx.get('direction', ''),
        amount=Decimal(str(ctx.get('amount', '0'))),
        subject_user_id=ctx.get('subject_user_id'),
        recipient_phone=ctx.get('recipient_phone', ''),
        idempotency_key=ctx.get('idempotency_key', ''),
        context_type=ctx.get('context_type', ''),
        context_id=ctx.get('context_id'),
        rule_id=ctx.get('rule_id'),
        reason=ctx.get('reason', ''),
    )
