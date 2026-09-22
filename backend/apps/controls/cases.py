"""Controls' side of a verification case: which movement it covers, and what
deciding it does to that movement and to the customer's request row.

``review._open_edd_case`` opens an EDD case when a movement is HELD, and raises
the ``VerificationRequest`` the customer answers; this is the other half. The
decision half used to live inline in
``apps.verification.service.decide_subject_case``, which meant the case ledger
wrote ``HeldMovement``, ``ControlOverride`` and ``VerificationRequest`` rows it
does not own (ADR-0033). Controls registers it instead, through
``apps.verification.hooks``.

The reaction runs inside the deciding transaction, so the release, the request
resolution and the case decision commit together or not at all — the same
guarantee the inline code had.
"""
from django.utils import timezone

from .models import ControlOverride, HeldMovement

#: How long an approval's pre-clearance stays usable.
OVERRIDE_TTL = timezone.timedelta(hours=72)


def held_movement_for(case):
    """The movement *case* was opened over, or None if it covers something else.

    Public because the ops console reads it to show a case's amount and reason.
    It lived as a private helper in ``apps.verification.service`` until ADR-0033;
    a HeldMovement lookup belongs to the app that owns HeldMovement.
    """
    if case.subject_type != 'HeldMovement' or not case.subject_id:
        return None
    return HeldMovement.objects.filter(pk=case.subject_id).first()


def _resolve_customer_request(case, action: str, reason: str) -> None:
    """Close the ``VerificationRequest`` ``_open_edd_case`` raised for *case*.

    Unconditional, exactly as it was when it ran inline in the case ledger: a
    case over something other than a HeldMovement simply has no request row, so
    the update matches nothing.
    """
    from apps.users.models import VerificationRequest

    VerificationRequest.objects.filter(case=case).exclude(
        status=VerificationRequest.Status.RESOLVED,
    ).update(status=VerificationRequest.Status.RESOLVED,
             resolved_at=timezone.now(),
             review_note=reason or ('Cleared' if action == 'approve' else ''))


def on_subject_case_decided(*, case, action: str, actor_label: str, reason: str) -> None:
    """Approve issues a single-use pre-clearance so the customer's retry passes
    the HOLD; either outcome closes the hold and the customer's request. A case
    over anything other than a HeldMovement has no movement to release."""
    _resolve_customer_request(case, action, reason)

    held = held_movement_for(case)
    if held is None:
        return

    if action == 'approve':
        ControlOverride.objects.create(
            user_id=case.user_id, op_type=held.op_type,
            max_amount=held.amount,
            expires_at=timezone.now() + OVERRIDE_TTL,
            source_case=str(case.id), held_movement=held,
            issued_by_label=actor_label[:120],
        )

    if held.status == held.Status.OPEN:
        held.status = (held.Status.RELEASED if action == 'approve'
                       else held.Status.REJECTED)
        held.reviewed_at = timezone.now()
        held.review_note = f"{actor_label}: {reason}" if reason else actor_label
        held.save(update_fields=['status', 'reviewed_at', 'review_note'])


def register() -> None:
    from apps.verification.hooks import register_subject_case_decided
    register_subject_case_decided(on_subject_case_decided)
