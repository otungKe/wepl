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
    """Aggregate root for one verification journey of one user.

    ``kyc_individual`` cases (one per KYC profile, opened on first submission,
    backfilled for pre-existing rows) verify identity; EDD case types verify a
    *thing* — a held large transaction, a large community drive — referenced
    generically via ``subject_type``/``subject_id`` (the AuditEvent target
    pattern), with ``kyc`` null. Periodic re-verification later opens a NEW
    linked case rather than mutating an approved one.
    """

    class State(models.TextChoices):
        SUBMITTED     = 'submitted',     'Submitted — awaiting review'
        REQUIRES_INFO = 'requires_info', 'Requires info — re-submission requested'
        APPROVED      = 'approved',      'Approved'
        REJECTED      = 'rejected',      'Rejected'

    class CaseType(models.TextChoices):
        KYC_INDIVIDUAL  = 'kyc_individual',  'KYC — individual identity'
        EDD_TRANSACTION = 'edd_transaction', 'EDD — large transaction'
        EDD_DRIVE       = 'edd_drive',       'EDD — large community drive'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='verification_cases',
    )
    # Set for kyc_individual cases only; EDD cases reference their subject below.
    kyc = models.ForeignKey(
        'users.KYCProfile', null=True, blank=True, on_delete=models.PROTECT,
        related_name='cases',
    )

    # What is being verified, for non-KYC cases. Generic reference (no FK —
    # subjects span models: FinancialTransaction, HeldMovement, a drive, …).
    subject_type = models.CharField(max_length=60, blank=True, default='')
    subject_id   = models.CharField(max_length=64, blank=True, default='')

    case_type = models.CharField(max_length=30, choices=CaseType.choices,
                                 default=CaseType.KYC_INDIVIDUAL, db_index=True)
    state     = models.CharField(max_length=20, choices=State.choices,
                                 default=State.SUBMITTED, db_index=True)

    # Monotonic per-case event sequence; advanced under row lock by the service.
    event_seq = models.PositiveIntegerField(default=0)

    # Working assignment (claim/release via the service — evented like every
    # other case change). Null = unassigned, anyone with the capability works it.
    assigned_to = models.ForeignKey(
        'backoffice.StaffAccount', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='assigned_verification_cases',
    )

    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-opened_at']
        indexes = [
            models.Index(fields=['state', 'opened_at'], name='vcase_state_opened_idx'),
            models.Index(fields=['subject_type', 'subject_id'], name='vcase_subject_idx'),
        ]
        constraints = [
            # A case verifies exactly one thing: identity (kyc set) or a
            # generic subject (subject_type set) — never neither.
            models.CheckConstraint(
                name='vcase_has_kyc_or_subject',
                condition=(models.Q(kyc__isnull=False)
                           | ~models.Q(subject_type='')),
            ),
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
        # KYC identity documents (snapshot from KYCProfile fields)
        ID_FRONT = 'id_front', 'Front of ID'
        ID_BACK  = 'id_back',  'Back of ID'
        SELFIE   = 'selfie',   'Selfie'
        # EDD evidence kinds (attached directly to a case)
        PROOF_OF_FUNDS = 'proof_of_funds', 'Proof of funds'
        BANK_STATEMENT = 'bank_statement', 'Bank statement'
        INVOICE        = 'invoice',        'Invoice'
        RECEIPT        = 'receipt',        'Receipt'
        SUPPORTING_DOC = 'supporting_doc', 'Supporting document'

    # The KYC subset that snapshot_documents() mirrors from KYCProfile fields.
    KYC_DOC_TYPES = ('id_front', 'id_back', 'selfie')

    class Source(models.TextChoices):
        SUBMISSION   = 'submission',   'Initial submission'
        RESUBMISSION = 'resubmission', 'Re-submission'
        BACKFILL     = 'backfill',     'Backfilled from legacy fields'

    case     = models.ForeignKey(VerificationCase, on_delete=models.PROTECT,
                                 related_name='documents')
    doc_type = models.CharField(max_length=20, choices=DocType.choices)
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


class OcrResult(models.Model):
    """One persisted automated-check outcome (V3). Every run is kept — including
    failures and superseded reads — so check history is queryable instead of
    living only in the latest ``KYCProfile.verification_detail`` blob."""

    case     = models.ForeignKey(VerificationCase, on_delete=models.PROTECT,
                                 related_name='ocr_results')
    # The exact document version that was read (null for legacy/degraded runs).
    document = models.ForeignKey(CaseDocument, null=True, blank=True,
                                 on_delete=models.PROTECT, related_name='ocr_results')

    engine   = models.CharField(max_length=40, blank=True, default='')
    detected = models.BooleanField(null=True, blank=True)

    id_number_match = models.BooleanField(null=True, blank=True)
    dob_match       = models.BooleanField(null=True, blank=True)

    raw = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"OcrResult({self.case_id}, {self.engine}, detected={self.detected})"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("OcrResult is append-only; runs are immutable.")
        return super().save(*args, **kwargs)


class CaseNote(models.Model):
    """Internal reviewer commentary on a case — never customer-visible.
    Append-only: the note trail is part of the review record."""

    case = models.ForeignKey(VerificationCase, on_delete=models.PROTECT,
                             related_name='notes')

    author_staff = models.ForeignKey(
        'backoffice.StaffAccount', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='verification_notes',
    )
    author_label = models.CharField(max_length=120, blank=True, default='')

    body = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"CaseNote({self.case_id}, {self.author_label})"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("CaseNote is append-only; notes cannot be edited.")
        return super().save(*args, **kwargs)


class RejectionReason(models.Model):
    """Coded rejection catalogue (V4). The operator picks a code; the customer
    sees the vetted ``customer_message``; analytics aggregate on ``code``.
    Free-text stays possible ('OTHER') but is the exception, not the norm."""

    code             = models.CharField(max_length=40, unique=True)
    label            = models.CharField(max_length=120)          # operator-facing
    customer_message = models.TextField()                        # applicant-facing
    active           = models.BooleanField(default=True)
    sort             = models.PositiveIntegerField(default=100)

    class Meta:
        ordering = ['sort', 'code']

    def __str__(self):
        return f"{self.code} — {self.label}"
