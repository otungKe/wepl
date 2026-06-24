"""File upload pipeline (ADR-0018): validate → store → record → enqueue scan.

The single sanctioned door for persisting user media. Validates declared content
type and size per file *kind*, computes a content checksum, stores via the
configured backend, and enqueues the (seam) virus scan. Magic-byte sniffing and a
real AV engine plug into the scan hook — see tasks.scan_file.
"""
import hashlib
import uuid

from django.core.exceptions import ValidationError

from .models import StoredFile

_MB = 1024 * 1024
_IMAGE = {'image/jpeg', 'image/png', 'image/webp', 'image/heic', 'image/heif'}
_DOC = _IMAGE | {'application/pdf'}
_MEDIA = _IMAGE | {'application/pdf', 'audio/mpeg', 'audio/aac', 'audio/mp4', 'video/mp4'}

# kind -> (allowed content types, max bytes)
KIND_RULES = {
    StoredFile.Kind.AVATAR:           (_IMAGE, 5 * _MB),
    StoredFile.Kind.COMMUNITY_PHOTO:  (_IMAGE, 5 * _MB),
    StoredFile.Kind.KYC_DOC:          (_DOC,   10 * _MB),
    StoredFile.Kind.PAYMENT_EVIDENCE: (_DOC,   10 * _MB),
    StoredFile.Kind.CHAT_ATTACHMENT:  (_MEDIA, 25 * _MB),
    StoredFile.Kind.OTHER:            (_DOC,   10 * _MB),
}


def _checksum(uploaded_file) -> str:
    h = hashlib.sha256()
    for chunk in uploaded_file.chunks():
        h.update(chunk)
    uploaded_file.seek(0)
    return h.hexdigest()


class FileService:

    @staticmethod
    def save(*, owner, kind, uploaded_file, tenant_id=None) -> StoredFile:
        """Validate and persist an uploaded file. Raises ValidationError on a
        disallowed kind, content type, or size."""
        if kind not in KIND_RULES:
            raise ValidationError(f"Unknown file kind '{kind}'.")
        allowed_types, max_bytes = KIND_RULES[kind]

        size = getattr(uploaded_file, 'size', 0) or 0
        if size <= 0:
            raise ValidationError("Empty file.")
        if size > max_bytes:
            raise ValidationError(
                f"File too large: {size} bytes (max {max_bytes} for {kind}).")

        content_type = (getattr(uploaded_file, 'content_type', '') or '').lower()
        if content_type not in allowed_types:
            raise ValidationError(
                f"Unsupported content type '{content_type}' for {kind}. "
                f"Allowed: {sorted(allowed_types)}")

        stored = StoredFile(
            owner=owner if getattr(owner, 'pk', None) else None,
            kind=kind,
            original_name=(getattr(uploaded_file, 'name', '') or '')[:255],
            content_type=content_type,
            size_bytes=size,
            checksum_sha256=_checksum(uploaded_file),
            created_key=uuid.uuid4().hex,
            tenant_id=tenant_id,
        )
        stored.file = uploaded_file
        stored.save()

        from .tasks import scan_file
        try:
            scan_file.delay(str(stored.id))
        except Exception:
            # Broker down — leave scan_status PENDING; the scan can be re-driven.
            pass
        return stored

    @staticmethod
    def soft_delete(stored: StoredFile) -> None:
        from django.utils import timezone
        if stored.deleted_at is None:
            stored.deleted_at = timezone.now()
            stored.save(update_fields=['deleted_at'])
