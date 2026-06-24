"""Stored-file model for the media pipeline (ADR-0018).

A single row per uploaded object — avatars, KYC docs, payment evidence, chat
attachments — with the metadata the pipeline needs: declared content type, size,
content checksum, virus-scan status, tenant, and a soft-delete marker for the
retention job. The bytes live in the configured storage backend (local FS in dev,
S3/R2 in prod) behind Django's storage abstraction.
"""
import uuid

from django.conf import settings
from django.db import models


def _upload_to(instance, filename):
    ext = ('.' + filename.rsplit('.', 1)[-1].lower())[:12] if '.' in filename else ''
    return f"{instance.kind}/{instance.created_key}{ext}"


class StoredFile(models.Model):

    class Kind(models.TextChoices):
        AVATAR           = 'avatar',           'Avatar'
        COMMUNITY_PHOTO  = 'community_photo',  'Community photo'
        KYC_DOC          = 'kyc_doc',          'KYC document'
        PAYMENT_EVIDENCE = 'payment_evidence', 'Payment evidence'
        CHAT_ATTACHMENT  = 'chat_attachment',  'Chat attachment'
        OTHER            = 'other',            'Other'

    class ScanStatus(models.TextChoices):
        PENDING  = 'pending',  'Pending scan'
        CLEAN    = 'clean',    'Clean'
        INFECTED = 'infected', 'Infected'
        SKIPPED  = 'skipped',  'Skipped (no scanner)'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='files',
    )
    kind          = models.CharField(max_length=20, choices=Kind.choices, db_index=True)
    original_name = models.CharField(max_length=255, blank=True, default='')
    content_type  = models.CharField(max_length=100, blank=True, default='')
    size_bytes    = models.BigIntegerField(default=0)
    checksum_sha256 = models.CharField(max_length=64, blank=True, default='', db_index=True)

    # Filled by _upload_to at create time (needs to be set before the FileField saves).
    created_key   = models.CharField(max_length=64, editable=False, default='')
    file          = models.FileField(upload_to=_upload_to, max_length=255)

    scan_status   = models.CharField(max_length=10, choices=ScanStatus.choices,
                                     default=ScanStatus.PENDING, db_index=True)

    tenant     = models.ForeignKey('tenants.Tenant', null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name='files')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['owner', 'kind'],       name='file_owner_kind_idx'),
            models.Index(fields=['deleted_at'],          name='file_deleted_idx'),
        ]

    def __str__(self):
        return f"StoredFile[{self.kind}] {self.original_name or self.id}"

    @property
    def is_available(self) -> bool:
        return self.deleted_at is None and self.scan_status != self.ScanStatus.INFECTED
