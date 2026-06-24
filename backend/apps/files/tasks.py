"""Files background tasks (ADR-0018): virus-scan seam + retention purge."""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name='apps.files.tasks.scan_file', queue='default')
def scan_file(file_id: str):
    """Virus-scan hook. With no scanner configured the file is marked SKIPPED
    (download blocks only on INFECTED, so this is non-regressive vs. today's
    no-scan behaviour). A real engine (ClamAV / a scanning API) sets CLEAN or
    INFECTED here, and may also do magic-byte content-type verification."""
    from django.conf import settings
    from .models import StoredFile

    try:
        stored = StoredFile.objects.get(id=file_id)
    except StoredFile.DoesNotExist:
        return

    scanner = getattr(settings, 'FILES_AV_SCANNER', None)
    if not scanner:
        stored.scan_status = StoredFile.ScanStatus.SKIPPED
        stored.save(update_fields=['scan_status'])
        return stored.scan_status

    # Seam: a configured scanner integration would inspect stored.file and set
    # CLEAN / INFECTED. Until one is wired, fail safe to SKIPPED.
    stored.scan_status = StoredFile.ScanStatus.SKIPPED
    stored.save(update_fields=['scan_status'])
    return stored.scan_status


@shared_task(name='apps.files.tasks.purge_expired_files', queue='default')
def purge_expired_files(retention_days: int = 30) -> int:
    """Hard-delete soft-deleted files past the retention window (storage + row)."""
    from datetime import timedelta
    from django.utils import timezone
    from .models import StoredFile

    cutoff = timezone.now() - timedelta(days=retention_days)
    purged = 0
    for stored in StoredFile.objects.filter(deleted_at__lt=cutoff).iterator():
        try:
            stored.file.delete(save=False)
        except Exception:
            logger.exception("purge_expired_files: storage delete failed for %s", stored.id)
        stored.delete()
        purged += 1
    logger.info("purge_expired_files: purged %d file(s)", purged)
    return purged
