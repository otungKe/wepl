"""Verification case ledger — "identity as a ledger" (V1+V2 of the CMS design).

The same discipline the money ledger applies to funds is applied here to
identity: immutable ``CaseEvent`` rows are the truth, ``VerificationCase.state``
is derived through a single transition service (``apps.verification.service``),
and documents are versioned ``CaseDocument`` rows that are never overwritten.
``KYCProfile`` remains the customer-facing projection; every state it reports
is now derived from a case transition, not mutated ad hoc.
"""
import uuid

from django.conf import settings
from django.db import models


class VerificationCase(models.Model):
    """Aggregate root for one identity-verification journey of one user.

    Exactly one case exists per KYC profile today (opened on first submission,
    backfilled for pre-existing rows). Periodic re-verification later opens a
    NEW linked case rather than mutating an approved one.
    """

    class State(models.TextChoices):
        SUBMITTED     = 'submitted',     'Submitted — awaiting review'
        REQUIRES_INFO = 'requires_info', 'Requires info — re-submission requested'
        APPROVED      = 'approved',      'Approved'
        REJECTED      = 'rejected',      'Rejected'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='verification_cases',
    )
    kyc = models.ForeignKey(
        'users.KYCProfile', on_delete=models.PROTECT,
        related_name='cases',
    )

    case_type = models.CharField(max_length=30, default='kyc_individual')
    state     = models.CharField(max_length=20, choices=State.choices,
                                 default=State.SUBMITTED, db_index=True)

    # Monotonic per-case event sequence; advanced under row lock by the service.
    event_seq = models.PositiveIntegerField(default=0)

    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-opened_at']
        indexes = [
            models.Index(fields=['state', 'opened_at'], name='vcase_state_opened_idx'),
        ]

    def __str__(self):
        return f"Case({self.user_id}, {self.case_type}, {self.state})"

    @property
    def is_terminal(self) -> bool:
        return self.state in (self.State.APPROVED, self.State.REJECTED)


class CaseEvent(models.Model):
    """One immutable entry in a case's timeline — the source of truth.

    Append-only like ``AuditEvent``/``JournalLine``: ``save()`` refuses updates
    and nothing deletes rows. ``seq`` is unique and monotonic per case.
    """

    class Actor(models.TextChoices):
        CUSTOMER = 'customer', 'Customer'
        STAFF    = 'staff',    'Staff'
        SYSTEM   = 'system',   'System'

    case = models.ForeignKey(VerificationCase, on_delete=models.PROTECT,
                             related_name='events')
    seq  = models.PositiveIntegerField()

    # e.g. case.opened / submission.received / checks.completed /
    # review.approved / review.rejected / review.info_requested / email.verified
    event_type = models.CharField(max_length=60, db_index=True)

    actor_kind  = models.CharField(max_length=10, choices=Actor.choices,
                                   default=Actor.SYSTEM)
    # Denormalised label captured at write time so the trail survives account
    # changes (phone number for customers, corporate email for staff,
    # provider name for system actors).
    actor_label = models.CharField(max_length=120, blank=True, default='')
    actor_user  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='verification_case_events',
    )
    actor_staff = models.ForeignKey(
        'backoffice.StaffAccount', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='verification_case_events',
    )

    # JSON-serialisable primitives only (mirrors the outbox payload rule).
    payload = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['case', 'seq']
        constraints = [
            models.UniqueConstraint(fields=['case', 'seq'], name='caseevent_case_seq_uniq'),
        ]

    def __str__(self):
        return f"CaseEvent({self.case_id}, #{self.seq}, {self.event_type})"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("CaseEvent is append-only; existing rows cannot be modified.")
        return super().save(*args, **kwargs)


class CaseDocument(models.Model):
    """One version of one identity document on a case — never overwritten.

    Django storage never reuses a name (``get_available_name`` uniquifies), so a
    re-submission that replaces ``KYCProfile.id_front`` leaves the previous
    object in storage; historically only the DB reference was lost. Each row
    here pins one storage object as an immutable version, so every document a
    decision was made against remains reviewable.
    """

    class DocType(models.TextChoices):
        ID_FRONT = 'id_front', 'Front of ID'
        ID_BACK  = 'id_back',  'Back of ID'
        SELFIE   = 'selfie',   'Selfie'

    class Source(models.TextChoices):
        SUBMISSION   = 'submission',   'Initial submission'
        RESUBMISSION = 'resubmission', 'Re-submission'
        BACKFILL     = 'backfill',     'Backfilled from legacy fields'

    case     = models.ForeignKey(VerificationCase, on_delete=models.PROTECT,
                                 related_name='documents')
    doc_type = models.CharField(max_length=12, choices=DocType.choices)
    version  = models.PositiveIntegerField()

    # References the storage object the KYC upload created; assigned by name,
    # never re-uploaded, never deleted by this app.
    file       = models.FileField(upload_to='verification/documents/', max_length=255)
    sha256     = models.CharField(max_length=64, blank=True, default='')
    size_bytes = models.BigIntegerField(null=True, blank=True)

    source      = models.CharField(max_length=14, choices=Source.choices,
                                   default=Source.SUBMISSION)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='verification_documents',
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['case', 'doc_type', 'version']
        constraints = [
            models.UniqueConstraint(fields=['case', 'doc_type', 'version'],
                                    name='casedoc_case_type_version_uniq'),
        ]

    def __str__(self):
        return f"CaseDocument({self.case_id}, {self.doc_type} v{self.version})"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("CaseDocument is append-only; versions are immutable.")
        return super().save(*args, **kwargs)
