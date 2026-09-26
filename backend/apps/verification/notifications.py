"""What a customer is told when a verification request is raised or resolved.

A verification request is verification's record (the customer-facing side of
an EDD case, or a follow-up compliance ask), so its announcement lives here
too. Controls raises one over a held movement; keeping the notice in
``apps.users`` made controls import users (boundary audit, step 7).

Goes through the durable event bus (ADR-0006).
"""
from apps.core.events import emit


def notify_verification_request(vreq, *, resolved=False):
    """Notify the user that a verification request was raised or resolved."""
    if resolved:
        emit(
            'verification_request_resolved',
            user_id=vreq.user_id,
            title='Verification updated',
            message=f'"{vreq.title}" has been resolved.'
                    + (f' {vreq.review_note}' if vreq.review_note else ''),
        )
    else:
        emit(
            'verification_request',
            user_id=vreq.user_id,
            title='Action needed: verification',
            message=f'{vreq.title} — open your Verification Center to respond.',
        )
