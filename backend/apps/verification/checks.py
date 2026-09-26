"""Running the automated identity check on a KYC submission.

The check is verification's work, not the customer app's: ask the active
``IdentityVerificationProvider`` (``apps.verification.identity``) what it makes
of the applicant, read the ID scan with the in-house OCR
(``apps.verification.ocr``), record both as a fact on the case timeline, and —
when the provider is conclusive — decide the case through ``service.decide()``.
It lived in ``apps/users/views/kyc.py`` until the boundary audit (step 6); the
two customer endpoints that submit evidence now just call it.

The provider's answer and the case decision are kept apart. The
``KYCProfile.verification_*`` fields hold what the provider said and nothing
else; a reviewer's approval or rejection lands in ``status``, ``reviewed_at``
and the case timeline, and no longer overwrites the provider's result.
"""
from __future__ import annotations

import logging

from django.utils import timezone

from . import service
from .identity import REJECTED, VERIFIED, IdentitySubject
from .identity.registry import get_provider

logger = logging.getLogger(__name__)


def read_id_scan_ocr(kyc) -> dict:
    """Advisory in-house OCR cross-check of the front ID scan against the typed
    values. Best-effort and never fatal — returns a detail dict for the reviewer;
    an empty/degraded result (no OCR backend) just means manual review proceeds."""
    from .ocr import run_id_ocr
    try:
        if not kyc.id_front:
            return {"detected": False, "engine": "none"}
        kyc.id_front.open('rb')
        try:
            image = kyc.id_front.read()
        finally:
            kyc.id_front.close()
        return run_id_ocr(
            image,
            id_number=kyc.id_number or '',
            date_of_birth=kyc.date_of_birth.isoformat() if kyc.date_of_birth else '',
        )
    except Exception as exc:
        logger.warning("ID-scan OCR failed for user %s: %s", kyc.user_id, exc)
        return {"detected": False, "engine": "error"}


def run_identity_check(kyc) -> None:
    """Run the active identity-verification provider against a KYC row and apply
    the outcome. Records the provider result for audit and derives the KYC status
    (VERIFIED→approved, REJECTED→rejected, MANUAL_REVIEW/PENDING→pending),
    notifying the applicant via the durable event bus on a terminal decision."""
    subject = IdentitySubject(
        id_number=kyc.id_number,
        given_names=kyc.given_names,
        surname=kyc.surname,
        date_of_birth=kyc.date_of_birth.isoformat() if kyc.date_of_birth else '',
        id_front_path=kyc.id_front.name if kyc.id_front else None,
        id_back_path=kyc.id_back.name if kyc.id_back else None,
        selfie_path=kyc.selfie.name if kyc.selfie else None,
    )

    try:
        result = get_provider().verify_identity(subject)
    except Exception as exc:
        # A vendor error must never lose the submission — fall back to human review.
        logger.exception("Identity check failed for user %s: %s", kyc.user_id, exc)
        kyc.status = 'pending'
        kyc.save(update_fields=['status'])
        return

    kyc.verification_provider   = result.provider
    kyc.verification_ref        = result.provider_ref
    kyc.verification_state      = result.state
    kyc.verification_detail     = {**(result.raw or {}), 'ocr': read_id_scan_ocr(kyc)}
    kyc.verification_checked_at = timezone.now()
    kyc.save(update_fields=[
        'verification_provider', 'verification_ref',
        'verification_state', 'verification_detail', 'verification_checked_at',
    ])

    # Record the check as a fact on the case timeline, then apply any terminal
    # outcome through the case state machine — the single door for decisions.
    # MANUAL_REVIEW / PENDING leave the case awaiting a human (or webhook),
    # status 'pending'.
    try:
        service.record_check(kyc, provider=result.provider, state=result.state,
                             detail=kyc.verification_detail)
        if result.state == VERIFIED:
            service.decide(kyc, 'approve', actor_label=result.provider)
        elif result.state == REJECTED:
            service.decide(kyc, 'reject', actor_label=result.provider,
                           reason=result.reason or 'Identity verification was not successful.')
        elif kyc.status != 'pending':
            kyc.status = 'pending'
            kyc.save(update_fields=['status'])
    except service.IllegalTransition as exc:
        # A check outcome that isn't applicable from the case's current state is
        # recorded (above) but not applied — a human resolves it in review.
        logger.warning("Identity-check outcome not applied for user %s: %s", kyc.user_id, exc)

    logger.info(
        "Identity check for user %s: provider=%s state=%s → status=%s",
        kyc.user_id, result.provider, result.state, kyc.status,
    )
