"""Backfill one verification case per existing KYC profile (CMS design V1).

State is derived with the same mapping the service uses; the opening event is
`case.backfilled` so backfilled timelines are distinguishable from organic
ones; the current KYC document fields are pinned as version-1 CaseDocuments
(source `backfill`) so history accrues from here on.
"""
import uuid

from django.db import migrations


def _state(kyc):
    if kyc.status in ('approved', 'rejected'):
        return kyc.status
    return 'requires_info' if kyc.resubmission_requested else 'submitted'


def forwards(apps, schema_editor):
    KYCProfile = apps.get_model('users', 'KYCProfile')
    VerificationCase = apps.get_model('verification', 'VerificationCase')
    CaseEvent = apps.get_model('verification', 'CaseEvent')
    CaseDocument = apps.get_model('verification', 'CaseDocument')

    for kyc in KYCProfile.objects.all().iterator():
        state = _state(kyc)
        case = VerificationCase.objects.create(
            id=uuid.uuid4(), user_id=kyc.user_id, kyc_id=kyc.id,
            case_type='kyc_individual', state=state, event_seq=1,
            closed_at=kyc.reviewed_at if state in ('approved', 'rejected') else None,
        )
        CaseEvent.objects.create(
            case=case, seq=1, event_type='case.backfilled',
            actor_kind='system', actor_label='migration',
            payload={
                'legacy_status': kyc.status,
                'resubmission_requested': list(kyc.resubmission_requested or []),
                'submitted_at': kyc.submitted_at.isoformat() if kyc.submitted_at else None,
            },
        )
        for doc_type in ('id_front', 'id_back', 'selfie'):
            name = getattr(kyc, doc_type).name if getattr(kyc, doc_type) else ''
            if name:
                CaseDocument.objects.create(
                    case=case, doc_type=doc_type, version=1,
                    file=name, source='backfill', uploaded_by_id=kyc.user_id,
                )


def backwards(apps, schema_editor):
    # Removes only what the backfill created; organic rows block the delete
    # via PROTECT on purpose — history is not disposable.
    VerificationCase = apps.get_model('verification', 'VerificationCase')
    CaseEvent = apps.get_model('verification', 'CaseEvent')
    CaseDocument = apps.get_model('verification', 'CaseDocument')
    backfilled = VerificationCase.objects.filter(
        event_seq=1, events__seq=1, events__event_type='case.backfilled',
    ).distinct()
    CaseDocument.objects.filter(case__in=backfilled).delete()
    CaseEvent.objects.filter(case__in=backfilled).delete()
    backfilled.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('verification', '0001_initial'),
        ('users', '0017_kycprofile_resubmission_requested'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
