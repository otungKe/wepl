import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(queue='default')
def erase_expired_identity_evidence():
    """Erase the identity evidence of closed accounts whose retention period has
    passed (``lifecycle.erase_identity_evidence``). Runs daily via Celery Beat."""
    from .lifecycle import erase_identity_evidence
    from .models import KYCProfile

    due = KYCProfile.objects.filter(evidence_retain_until__lte=timezone.localdate())
    n = 0
    for kyc in due.iterator():
        with transaction.atomic():
            erase_identity_evidence(kyc)
        n += 1
    if n:
        logger.info("Erased identity evidence for %d closed account(s)", n)
    return n
