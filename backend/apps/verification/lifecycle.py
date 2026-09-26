"""Verification's part in closing an account and exporting its data
(``apps.core.lifecycle``, boundary audit step 8).

Identity evidence (names, ID number, date of birth, address, KRA PIN, the ID
scans, the selfie and every document on the customer's cases) is what an
anti-money-laundering examiner asks for, so closing an account does not erase
it: it stamps ``evidence_retain_until`` and ``tasks.erase_expired_identity_evidence``
erases it when that date passes. What is not identity evidence (email and its
tokens, referral code) goes at once.
"""
import datetime
import logging

from django.db import transaction
from django.utils import timezone

from apps.core import lifecycle

from .models import CaseDocument, CaseEvent, KYCProfile, OcrResult, VerificationCase, VerificationRequest
from .service import _append

logger = logging.getLogger(__name__)

EVIDENCE_RETENTION_YEARS = 7
ERASED_DOB = datetime.date(1900, 1, 1)


def _retain_until(today: datetime.date) -> datetime.date:
    try:
        return today.replace(year=today.year + EVIDENCE_RETENTION_YEARS)
    except ValueError:  # 29 February
        return today.replace(year=today.year + EVIDENCE_RETENTION_YEARS, day=28)


def _stamp_cases(user_id, event_type, payload) -> None:
    """Put the lifecycle step on every case's timeline, the verification
    context's own audit trail."""
    for case in VerificationCase.objects.filter(user_id=user_id):
        _append(case, event_type, actor_kind=CaseEvent.Actor.SYSTEM,
                actor_label='account lifecycle', payload=payload)


def erase(user) -> None:
    retain_until = _retain_until(timezone.localdate())
    KYCProfile.objects.filter(user=user).update(
        email='', email_verified=False, email_verification_token='',
        referral_code='', evidence_retain_until=retain_until,
    )
    _stamp_cases(user.id, 'account.closed', {'evidence_retain_until': retain_until.isoformat()})


def erase_identity_evidence(kyc) -> None:
    """Erase every piece of identity evidence about ``kyc``'s customer. The
    rows stay, so the case timeline and the ledger still resolve; the personal
    data and the stored files do not. Deliberately bypasses the append-only
    ``save()`` guards on documents and OCR runs: erasure is the one sanctioned
    exception, and it is recorded on each case's timeline. Run it inside a
    transaction."""
    user_id = kyc.user_id
    files = [(getattr(kyc, f).storage, getattr(kyc, f).name)
             for f in ('id_front', 'id_back', 'selfie') if getattr(kyc, f)]
    for doc in CaseDocument.objects.filter(case__user_id=user_id).exclude(file=''):
        files.append((doc.file.storage, doc.file.name))
    for req in VerificationRequest.objects.filter(user_id=user_id).exclude(document='') \
            .exclude(document__isnull=True):
        files.append((req.document.storage, req.document.name))

    KYCProfile.objects.filter(pk=kyc.pk).update(
        given_names='[deleted]', surname='[deleted]', id_number=f'DELETED-{user_id}',
        date_of_birth=ERASED_DOB, email='', kra_pin='', physical_address='',
        occupation='[deleted]', referral_code='', rejection_reason='',
        id_front='', id_back=None, selfie=None,
        verification_detail={}, email_verification_token='', resubmission_requested=[],
        evidence_retain_until=None,
    )
    CaseDocument.objects.filter(case__user_id=user_id).update(file='')
    OcrResult.objects.filter(case__user_id=user_id).update(raw={})
    VerificationRequest.objects.filter(user_id=user_id).update(response_note='', document=None)
    _stamp_cases(user_id, 'evidence.erased', {})

    def _delete_files():
        for storage, name in dict.fromkeys(files):
            try:
                storage.delete(name)
            except Exception:
                logger.warning("Could not delete identity evidence file %s", name)
    transaction.on_commit(_delete_files)


def export(user) -> dict:
    k = KYCProfile.objects.filter(user=user).first()
    if k is None:
        return {"identity_verification": {"status": "not_submitted"}}
    return {"identity_verification": {
        "status": k.status,
        "given_names": k.given_names,
        "surname": k.surname,
        "kra_pin": k.kra_pin,
        "county": k.county,
        "physical_address": k.physical_address,
        "email_verified": k.email_verified,
        "submitted_at": k.submitted_at.isoformat() if k.submitted_at else None,
    }}


def register() -> None:
    lifecycle.register("verification", erase=erase, export=export)
