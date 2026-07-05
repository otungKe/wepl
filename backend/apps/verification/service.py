"""The single door a verification case walks through (V1 of the CMS design).

Mirrors ``post_journal()`` for the money ledger: every state change appends an
immutable ``CaseEvent`` under a row lock, the case ``state`` advances only
through declared transitions, and the customer-facing ``KYCProfile`` fields are
updated as a projection of the case — never the other way round.

Callers:
  - customer submit / targeted re-submit (``apps.users.views.kyc``)
  - the identity-check pipeline (``_run_identity_check``)
  - ops console decisions (``apps.backoffice.views_verification``)
  - Django-admin KYC actions (``apps.users.admin``)
"""
from __future__ import annotations

import hashlib
import logging

from django.db import transaction
from django.utils import timezone

from .models import CaseDocument, CaseEvent, VerificationCase

logger = logging.getLogger(__name__)

_DOC_FIELDS = [c[0] for c in CaseDocument.DocType.choices]  # id_front, id_back, selfie

S = VerificationCase.State

# (state, action) -> next state. An action absent for a state is illegal.
# Self-transitions are deliberate: request_info on a decided case records the
# ask without revoking the decision (matches the long-standing admin action),
# and resubmit while still submitted covers a user re-posting the full form.
_TRANSITIONS = {
    (S.SUBMITTED,     'approve'):      S.APPROVED,
    (S.SUBMITTED,     'reject'):       S.REJECTED,
    (S.SUBMITTED,     'request_info'): S.REQUIRES_INFO,
    (S.SUBMITTED,     'resubmit'):     S.SUBMITTED,
    (S.REQUIRES_INFO, 'approve'):      S.APPROVED,
    (S.REQUIRES_INFO, 'reject'):       S.REJECTED,
    (S.REQUIRES_INFO, 'request_info'): S.REQUIRES_INFO,
    (S.REQUIRES_INFO, 'resubmit'):     S.SUBMITTED,
    (S.REJECTED,      'resubmit'):     S.SUBMITTED,
    (S.REJECTED,      'request_info'): S.REJECTED,
    (S.REJECTED,      'approve'):      S.APPROVED,   # reversal after reconsideration
    (S.APPROVED,      'request_info'): S.APPROVED,
    (S.APPROVED,      'resubmit'):     S.SUBMITTED,  # targeted top-up re-enters review
    (S.APPROVED,      'reject'):       S.REJECTED,   # revocation (compliance)
}

_REVIEW_EVENT = {
    'approve':      'review.approved',
    'reject':       'review.rejected',
    'request_info': 'review.info_requested',
}


class IllegalTransition(Exception):
    """Raised when an action is not legal from the case's current state."""

    def __init__(self, state: str, action: str):
        self.state, self.action = state, action
        super().__init__(f"Action {action!r} is not legal from state {state!r}.")


# ─────────────────────────────────────────────────────────────
# Case access + event append
# ─────────────────────────────────────────────────────────────

def case_for(kyc) -> VerificationCase:
    """Return the (single) case for a KYC profile, opening one if missing.

    Pre-CMS rows get a case lazily with state derived from the legacy status —
    the same mapping the backfill migration applies.
    """
    case = VerificationCase.objects.filter(kyc=kyc).order_by('-opened_at').first()
    if case:
        return case
    with transaction.atomic():
        case = VerificationCase.objects.create(
            user_id=kyc.user_id, kyc=kyc, state=_state_from_kyc(kyc),
            closed_at=kyc.reviewed_at if kyc.status in ('approved', 'rejected') else None,
        )
        _append(case, 'case.opened', actor_kind=CaseEvent.Actor.SYSTEM,
                actor_label='system', payload={'legacy_status': kyc.status})
    return case


def _state_from_kyc(kyc) -> str:
    if kyc.status in (S.APPROVED, S.REJECTED):
        return kyc.status
    return S.REQUIRES_INFO if kyc.resubmission_requested else S.SUBMITTED


def _append(case, event_type, *, actor_kind, actor_label='', actor_user=None,
            actor_staff=None, payload=None) -> CaseEvent:
    """Append one event with the next per-case sequence number.

    Must run inside a transaction; the SELECT ... FOR UPDATE on the case row
    serialises concurrent writers so ``seq`` stays gap-aware and monotonic.
    """
    locked = VerificationCase.objects.select_for_update().get(pk=case.pk)
    locked.event_seq += 1
    locked.save(update_fields=['event_seq'])
    case.event_seq = locked.event_seq
    return CaseEvent.objects.create(
        case=case, seq=locked.event_seq, event_type=event_type,
        actor_kind=actor_kind, actor_label=actor_label[:120],
        actor_user=actor_user, actor_staff=actor_staff, payload=payload or {},
    )


# ─────────────────────────────────────────────────────────────
# Document versioning (V2 — kills the overwrite bug)
# ─────────────────────────────────────────────────────────────

def _sha256(field_file) -> tuple[str, int | None]:
    """Best-effort content hash + size; never fatal (storage may be remote/slow)."""
    try:
        field_file.open('rb')
        try:
            h = hashlib.sha256()
            size = 0
            for chunk in iter(lambda: field_file.read(1024 * 1024), b''):
                h.update(chunk)
                size += len(chunk)
            return h.hexdigest(), size
        finally:
            field_file.close()
    except Exception:
        return '', None


def snapshot_documents(case, kyc, *, source, uploaded_by=None) -> list[dict]:
    """Pin the storage objects the KYC fields currently reference as immutable
    versions. Idempotent: a field whose storage name is already the latest
    version is skipped, so re-running never duplicates."""
    captured = []
    for doc_type in _DOC_FIELDS:
        field_file = getattr(kyc, doc_type, None)
        if not field_file or not field_file.name:
            continue
        latest = (CaseDocument.objects
                  .filter(case=case, doc_type=doc_type)
                  .order_by('-version').first())
        if latest and latest.file.name == field_file.name:
            continue
        sha, size = _sha256(field_file)
        doc = CaseDocument(
            case=case, doc_type=doc_type,
            version=(latest.version + 1) if latest else 1,
            sha256=sha, size_bytes=size, source=source, uploaded_by=uploaded_by,
        )
        doc.file.name = field_file.name  # pin the existing object; no re-upload
        doc.save()
        captured.append({'doc_type': doc_type, 'version': doc.version,
                         'sha256': sha[:16]})
    return captured


# ─────────────────────────────────────────────────────────────
# Recording (customer + system facts)
# ─────────────────────────────────────────────────────────────

def record_submission(kyc, *, kind, items=None) -> VerificationCase:
    """Record a customer submission (initial, full re-post, or targeted top-up)
    and advance the case to SUBMITTED. Snapshots any new document versions."""
    with transaction.atomic():
        case = case_for(kyc)
        source = (CaseDocument.Source.RESUBMISSION if kind != 'initial'
                  else CaseDocument.Source.SUBMISSION)
        docs = snapshot_documents(case, kyc, source=source, uploaded_by=kyc.user)
        payload = {'kind': kind, 'documents': docs}
        if items:
            payload['items'] = list(items)
        if kind == 'initial':
            _append(case, 'submission.received',
                    actor_kind=CaseEvent.Actor.CUSTOMER,
                    actor_label=kyc.user.phone_number, actor_user=kyc.user,
                    payload=payload)
        else:
            _transition(case, 'resubmit',
                        actor_kind=CaseEvent.Actor.CUSTOMER,
                        actor_label=kyc.user.phone_number, actor_user=kyc.user,
                        payload=payload)
        return case


def record_check(kyc, *, provider, state, detail=None) -> None:
    """Record an automated check outcome (identity provider + OCR) as a fact on
    the timeline. Terminal decisions are applied separately via ``decide()``."""
    with transaction.atomic():
        case = case_for(kyc)
        ocr = (detail or {}).get('ocr') or {}
        _append(case, 'checks.completed', actor_kind=CaseEvent.Actor.SYSTEM,
                actor_label=provider,
                payload={'provider': provider, 'state': state,
                         'ocr_detected': ocr.get('detected'),
                         'ocr_mismatch': bool(ocr.get('mismatch'))})


def record_email_verified(kyc) -> None:
    with transaction.atomic():
        case = case_for(kyc)
        _append(case, 'email.verified', actor_kind=CaseEvent.Actor.CUSTOMER,
                actor_label=kyc.user.phone_number, actor_user=kyc.user,
                payload={'email': kyc.email})


# ─────────────────────────────────────────────────────────────
# Deciding (the chokepoint)
# ─────────────────────────────────────────────────────────────

def decide(kyc, action, *, actor_label, staff=None, reviewer_user=None,
           reason='', items=None, notify=True) -> VerificationCase:
    """Apply a review decision through the state machine and project it onto
    ``KYCProfile``. Raises ``IllegalTransition`` if the action isn't legal.

    action: 'approve' | 'reject' | 'request_info'
    """
    if action not in _REVIEW_EVENT:
        raise ValueError(f"Unknown decision action: {action!r}")

    with transaction.atomic():
        case = case_for(kyc)
        actor_kind = CaseEvent.Actor.STAFF if (staff or reviewer_user) else CaseEvent.Actor.SYSTEM
        payload = {}
        if reason:
            payload['reason'] = reason
        if items is not None:
            payload['items'] = list(items)
        _transition(case, action, actor_kind=actor_kind, actor_label=actor_label,
                    actor_user=reviewer_user, actor_staff=staff, payload=payload,
                    event_type=_REVIEW_EVENT[action])
        _project(kyc, case, action, actor_label=actor_label,
                 reviewer_user=reviewer_user, reason=reason, items=items)

    if notify:
        _notify(kyc, action)
    return case


def _transition(case, action, *, event_type=None, **event_kwargs) -> None:
    nxt = _TRANSITIONS.get((case.state, action))
    if nxt is None:
        raise IllegalTransition(case.state, action)
    _append(case, event_type or f'case.{action}', **event_kwargs)
    update = ['state']
    case.state = nxt
    if nxt in (S.APPROVED, S.REJECTED):
        case.closed_at = timezone.now()
        update.append('closed_at')
    elif case.closed_at:
        case.closed_at = None  # re-opened by a re-submission
        update.append('closed_at')
    case.save(update_fields=update)


def _project(kyc, case, action, *, actor_label, reviewer_user, reason, items):
    """Derive the customer-facing KYCProfile fields from the decided case."""
    now = timezone.now()
    fields = []
    if action == 'approve':
        kyc.status, kyc.rejection_reason = 'approved', ''
        kyc.resubmission_requested = []
        fields += ['status', 'rejection_reason', 'resubmission_requested']
    elif action == 'reject':
        kyc.status = 'rejected'
        kyc.rejection_reason = reason or (
            'Your documents could not be verified. Please re-submit clear photos of your ID.')
        fields += ['status', 'rejection_reason']
    elif action == 'request_info':
        # Deliberately does NOT change kyc.status — an approved user keeps
        # access until they top up (long-standing behaviour).
        kyc.resubmission_requested = list(items or [])
        fields += ['resubmission_requested']

    if action in ('approve', 'reject'):
        kyc.reviewed_at = now
        kyc.verification_provider = actor_label
        kyc.verification_state = 'verified' if action == 'approve' else 'rejected'
        kyc.verification_checked_at = now
        fields += ['reviewed_at', 'verification_provider',
                   'verification_state', 'verification_checked_at']
        if reviewer_user is not None:
            kyc.reviewed_by = reviewer_user
            fields.append('reviewed_by')
    kyc.save(update_fields=fields)


def _notify(kyc, action):
    # Lazy import: apps.users.admin also imports this module for its actions.
    from apps.users.admin import _notify_kyc_decision, _notify_resubmission_request
    if action in ('approve', 'reject'):
        _notify_kyc_decision(kyc)
    elif action == 'request_info' and kyc.resubmission_requested:
        _notify_resubmission_request(kyc)
