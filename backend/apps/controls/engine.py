"""
Controls engine — limits & velocity evaluation at the posting chokepoint.

`enforce_controls()` is called by post_journal() before any journal is written.
It classifies the movement (pay-in / pay-out), evaluates every active LimitRule,
writes a ControlDecision audit row, and raises a typed exception on DENY/HOLD so
the journal is never written.

Decision precedence: a DENY by any rule short-circuits; otherwise the strictest
outcome wins (HOLD over ALLOW). All decisions are logged and persisted.
"""
import logging
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.utils import timezone

from apps.core.exceptions import ControlHeld, LimitExceeded
from apps.ledger.models import FinancialTransaction

from .models import ControlDecision, LimitRule

logger = logging.getLogger(__name__)

OpType = FinancialTransaction.OpType
State = FinancialTransaction.State

# Money flowing INTO the platform from a member.
PAYIN_OPS = frozenset({
    OpType.CONTRIBUTION, OpType.WELFARE_CONTRIBUTION,
    OpType.SHARES_PURCHASE, OpType.ADVANCE_REPAYMENT,
})
# Money flowing OUT to a member.
PAYOUT_OPS = frozenset({
    OpType.DISBURSEMENT, OpType.STANDING_ORDER, OpType.ROSCA_PAYOUT,
    OpType.ADVANCE_DISBURSEMENT, OpType.WELFARE_CLAIM,
})

# Movements already in flight or settled count toward a window.
_COUNTED_STATES = [State.PENDING, State.PROCESSING, State.SUCCESS]


def classify_direction(op_type: str) -> str | None:
    if op_type in PAYIN_OPS:
        return LimitRule.Direction.PAYIN
    if op_type in PAYOUT_OPS:
        return LimitRule.Direction.PAYOUT
    return None


def _ops_for(direction: str) -> frozenset:
    return PAYIN_OPS if direction == LimitRule.Direction.PAYIN else PAYOUT_OPS


def _window_start(period: str, now):
    if period == LimitRule.Period.HOUR:
        return now - timedelta(hours=1)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == LimitRule.Period.DAY:
        return midnight
    if period == LimitRule.Period.WEEK:
        return midnight - timedelta(days=now.weekday())
    if period == LimitRule.Period.MONTH:
        return midnight.replace(day=1)
    return None  # TXN — no window


def _window_totals(*, rule, direction, op_type, subject_user_id, now, exclude_ft_id) -> tuple[Decimal, int]:
    """Sum prior in-window movements (excluding the current one)."""
    ops = {op_type} if rule.op_type else _ops_for(direction)
    qs = FinancialTransaction.objects.filter(op_type__in=ops, state__in=_COUNTED_STATES)
    start = _window_start(rule.period, now)
    if start is not None:
        qs = qs.filter(created_at__gte=start)
    if rule.scope == LimitRule.Scope.PER_USER:
        qs = qs.filter(initiated_by_id=subject_user_id)
    if exclude_ft_id is not None:
        qs = qs.exclude(pk=exclude_ft_id)
    agg = qs.aggregate(total=Sum('amount'), cnt=Count('id'))
    return (agg['total'] or Decimal('0')), (agg['cnt'] or 0)


def evaluate(*, subject_user_id, op_type, direction, amount, financial_transaction=None) -> ControlDecision:
    """Evaluate all active rules and persist + return a ControlDecision."""
    amount = amount if isinstance(amount, Decimal) else Decimal(str(amount))
    now = timezone.now()
    ft_id = getattr(financial_transaction, 'pk', None)

    outcome = ControlDecision.Outcome.ALLOW
    reason = 'Within limits'
    matched = None
    win_amount = None
    win_count = None

    rules = LimitRule.objects.filter(is_active=True).filter(
        direction__in=[LimitRule.Direction.ANY, direction]
    ).order_by('priority', 'id')

    for rule in rules:
        if rule.op_type and rule.op_type != op_type:
            continue
        if rule.period == LimitRule.Period.TXN:
            cur_amount, cur_count = amount, 1
        else:
            prior_amount, prior_count = _window_totals(
                rule=rule, direction=direction, op_type=op_type,
                subject_user_id=subject_user_id, now=now, exclude_ft_id=ft_id,
            )
            cur_amount, cur_count = prior_amount + amount, prior_count + 1

        violated, why = False, ''
        if rule.max_amount is not None and cur_amount > rule.max_amount:
            violated = True
            why = f"{rule.get_period_display()} {direction.lower()} total {cur_amount} exceeds limit {rule.max_amount}"
        elif rule.max_count is not None and cur_count > rule.max_count:
            violated = True
            why = f"{rule.get_period_display()} {direction.lower()} count {cur_count} exceeds limit {rule.max_count}"

        if not violated:
            continue

        if rule.action == LimitRule.Action.DENY:
            outcome, reason, matched, win_amount, win_count = (
                ControlDecision.Outcome.DENY, why, rule, cur_amount, cur_count)
            break  # DENY short-circuits
        elif outcome != ControlDecision.Outcome.DENY:
            outcome, reason, matched, win_amount, win_count = (
                ControlDecision.Outcome.HOLD, why, rule, cur_amount, cur_count)

    decision = ControlDecision.objects.create(
        decision=outcome, op_type=op_type, direction=direction, amount=amount,
        subject_user_id=subject_user_id, financial_transaction=financial_transaction,
        rule=matched, reason=reason, window_amount=win_amount, window_count=win_count,
    )
    if outcome != ControlDecision.Outcome.ALLOW:
        logger.warning("Control %s for user=%s op=%s amount=%s: %s",
                       outcome, subject_user_id, op_type, amount, reason)
    return decision


def enforce_controls(*, financial_transaction, amount) -> ControlDecision | None:
    """Chokepoint entrypoint. Raises LimitExceeded (DENY) / ControlHeld (HOLD).

    Returns the decision on ALLOW, or None for movements with no classified
    direction (internal moves, fees) which bypass member-facing controls.
    """
    op_type = financial_transaction.op_type
    direction = classify_direction(op_type)
    if direction is None:
        return None

    decision = evaluate(
        subject_user_id=financial_transaction.initiated_by_id,
        op_type=op_type, direction=direction, amount=amount,
        financial_transaction=financial_transaction,
    )
    if decision.decision in (ControlDecision.Outcome.DENY, ControlDecision.Outcome.HOLD):
        # Build a context snapshot now — the FinancialTransaction will be rolled
        # back with the service's transaction, so the review queue is rebuilt from
        # these primitives by the exception handler (see apps/controls/review.py).
        ft = financial_transaction
        context = {
            'decision': decision.decision,
            'op_type': op_type,
            'direction': direction,
            'amount': str(amount),
            'subject_user_id': ft.initiated_by_id,
            'recipient_phone': ft.recipient_phone or '',
            'idempotency_key': ft.idempotency_key or '',
            'context_type': ft.context_type or '',
            'context_id': ft.context_id,
            'rule_id': decision.rule_id,
            'reason': decision.reason,
        }
        if decision.decision == ControlDecision.Outcome.DENY:
            raise LimitExceeded(decision.reason, context=context)
        raise ControlHeld(decision.reason, context=context)
    return decision
