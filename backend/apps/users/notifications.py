"""Customer-facing notifications about a user's identity and compliance state.

These lived in ``apps/users/admin.py`` until ADR-0033. Two of them are called
from ``apps.verification.service`` when a KYC case is decided, which meant the
case ledger imported another app's **admin module** to reach private helpers —
the last wrong-way edge keeping ``apps.verification`` inside the import cycle.
They live here now, and verification announces the decision through
``apps.verification.hooks`` instead; ``UsersConfig.ready()`` registers
``on_kyc_decided`` below.

Every one of these goes through the durable event bus (ADR-0006), so a crash
between the decision and the notification does not lose it.
"""
from apps.core.events import emit

from apps.verification.models import KYCProfile


def notify_kyc_decision(kyc):
    """Tell the applicant their KYC was approved/rejected (in-app notification)."""
    if kyc.status == 'approved':
        emit(
            'kyc_approved',
            user_id=kyc.user_id,
            title='Identity verified ✅',
            message='Your KYC has been approved — you now have full access to '
                    'payments, contributions, and community features.',
        )
    elif kyc.status == 'rejected':
        reason = kyc.rejection_reason or 'Please re-submit your documents.'
        emit(
            'kyc_rejected',
            user_id=kyc.user_id,
            title='KYC needs attention',
            message=f'Your identity verification was not approved. {reason}',
        )


def notify_resubmission_request(kyc):
    """Tell the user which KYC items they've been asked to re-provide, and send
    them to the targeted re-submission screen (they don't re-fill the whole form)."""
    labels = dict(KYCProfile.RESUBMITTABLE_ITEMS)
    items = ', '.join(labels.get(k, k) for k in (kyc.resubmission_requested or []))
    emit(
        'kyc_resubmission_requested',
        user_id=kyc.user_id,
        title='Action needed: re-submit KYC items',
        message=f'Please re-submit the following in WEPL: {items}. '
                f'You only need to provide these — the rest of your details stay as they are.',
    )


def on_kyc_decided(*, kyc, action: str) -> None:
    """Announce a decided KYC case to its applicant.

    Registered against ``apps.verification.hooks``; this is the body of what
    ``verification.service._notify`` used to call inline, unchanged.
    """
    if action in ('approve', 'reject'):
        notify_kyc_decision(kyc)
    elif action == 'request_info' and kyc.resubmission_requested:
        notify_resubmission_request(kyc)


def register() -> None:
    """Called once, from ``UsersConfig.ready()``."""
    from apps.verification.hooks import register_kyc_decided
    register_kyc_decided(on_kyc_decided)
