"""Held/denied movement review queue.

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
    held = HeldMovement.objects.create(
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
    if held.decision == HeldMovement.Decision.HOLD and held.subject_user_id:
        _open_edd_case(held)
    return held


def _open_edd_case(held: HeldMovement) -> None:
    """A HOLD starts evidence collection: open an EDD case over the held
    movement and raise the customer-facing request (the mobile Verification
    Center's "Requests & documents" section). Best-effort — a failure here
    must never break the error response the customer is already receiving."""
    try:
        from apps.users.models import VerificationRequest
        from apps.verification import service as case_service
        from apps.verification.models import VerificationCase

        case = case_service.open_subject_case(
            held.subject_user, case_type=VerificationCase.CaseType.EDD_TRANSACTION,
            subject_type='HeldMovement', subject_id=held.pk,
            requested_items=['proof_of_funds', 'supporting_doc'],
            actor_label='controls',
        )
        # One customer-facing request per open case.
        if VerificationRequest.objects.filter(case=case).exclude(
                status=VerificationRequest.Status.RESOLVED).exists():
            return
        vreq = VerificationRequest.objects.create(
            user=held.subject_user, case=case,
            kind=VerificationRequest.Kind.TRANSACTION_DOCS,
            title='Supporting documents needed for your transaction',
            detail=(f'Your {held.op_type.replace("_", " ")} of KES {held.amount} '
                    'needs a quick review before it can go through. Please upload '
                    'a document showing the source of these funds — for example a '
                    'bank or mobile-money statement, an invoice, or a receipt — '
                    'and add a short note if helpful.'),
        )
        from apps.users.admin import _notify_verification_request
        _notify_verification_request(vreq)
    except Exception:
        logger.exception("Failed to open EDD case for held movement %s", held.pk)
