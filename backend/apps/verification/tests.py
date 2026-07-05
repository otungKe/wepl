"""Verification case ledger tests — the identity analogue of the posting tests.

Covers: case opening + event sequencing, document versioning (the overwrite
bug fix), the transition table, projection onto KYCProfile, and the ops
decision endpoint routing through the single door.
"""
import io
from datetime import date

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from apps.backoffice.auth import issue_staff_token
from apps.backoffice.models import StaffAccount
from apps.users.models import KYCProfile

from . import service
from .models import CaseDocument, CaseEvent, VerificationCase

User = get_user_model()


def _png(name='doc.png'):
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (8, 8), 'white').save(buf, format='PNG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/png')


def _kyc(phone='+254700000001', id_number='11111111', **overrides):
    user = User.objects.create_user(phone_number=phone, is_phone_verified=True)
    fields = dict(
        user=user, given_names='Wanjiku', surname='Kamau',
        id_number=id_number, date_of_birth=date(1990, 1, 1),
        county='Nairobi', physical_address='Moi Ave 1', occupation='Trader',
        source_of_income='business', expected_monthly_income='under_250k',
        id_front=_png('front.png'), id_back=_png('back.png'), selfie=_png('selfie.png'),
        status='pending',
    )
    fields.update(overrides)
    return KYCProfile.objects.create(**fields)


class CaseLedgerTests(TestCase):

    def test_case_for_opens_case_lazily_with_derived_state(self):
        kyc = _kyc()
        case = service.case_for(kyc)
        self.assertEqual(case.state, VerificationCase.State.SUBMITTED)
        self.assertEqual(case.events.get(seq=1).event_type, 'case.opened')
        # Second call returns the same case — no duplicates.
        self.assertEqual(service.case_for(kyc).pk, case.pk)
        self.assertEqual(VerificationCase.objects.filter(kyc=kyc).count(), 1)

    def test_record_submission_snapshots_document_versions(self):
        kyc = _kyc()
        case = service.record_submission(kyc, kind='initial')
        docs = CaseDocument.objects.filter(case=case)
        self.assertEqual(set(docs.values_list('doc_type', flat=True)),
                         {'id_front', 'id_back', 'selfie'})
        self.assertTrue(all(d.version == 1 for d in docs))
        self.assertTrue(all(d.sha256 for d in docs))

    def test_resubmission_versions_never_overwrite(self):
        """The critical fix: replacing a document keeps the prior version."""
        kyc = _kyc()
        service.record_submission(kyc, kind='initial')
        v1_name = CaseDocument.objects.get(doc_type='id_front').file.name

        kyc.id_front = _png('front-take-2.png')
        kyc.save()
        service.record_submission(kyc, kind='targeted_resubmit', items=['id_front'])

        fronts = CaseDocument.objects.filter(doc_type='id_front').order_by('version')
        self.assertEqual([d.version for d in fronts], [1, 2])
        self.assertEqual(fronts[0].file.name, v1_name)       # v1 retained
        self.assertNotEqual(fronts[1].file.name, v1_name)    # v2 is the new object
        # Unchanged documents don't gain redundant versions.
        self.assertEqual(CaseDocument.objects.filter(doc_type='selfie').count(), 1)

    def test_event_seq_is_monotonic_and_events_immutable(self):
        kyc = _kyc()
        service.record_submission(kyc, kind='initial')
        service.record_email_verified(kyc)
        service.record_check(kyc, provider='fake', state='manual_review')
        seqs = list(CaseEvent.objects.filter(case__kyc=kyc)
                    .order_by('seq').values_list('seq', flat=True))
        self.assertEqual(seqs, list(range(1, len(seqs) + 1)))
        ev = CaseEvent.objects.first()
        ev.event_type = 'tampered'
        with self.assertRaises(ValueError):
            ev.save()

    def test_decide_approve_projects_onto_kyc(self):
        kyc = _kyc()
        case = service.decide(kyc, 'approve', actor_label='manual (admin)')
        self.assertEqual(case.state, VerificationCase.State.APPROVED)
        self.assertIsNotNone(case.closed_at)
        kyc.refresh_from_db()
        self.assertEqual(kyc.status, 'approved')
        self.assertEqual(kyc.verification_state, 'verified')
        self.assertEqual(case.events.order_by('-seq').first().event_type, 'review.approved')

    def test_decide_reject_requires_info_and_illegal_transitions(self):
        kyc = _kyc()
        service.decide(kyc, 'request_info', actor_label='ops:a@wepl.app',
                       items=['selfie'])
        kyc.refresh_from_db()
        case = service.case_for(kyc)
        self.assertEqual(case.state, VerificationCase.State.REQUIRES_INFO)
        self.assertEqual(kyc.resubmission_requested, ['selfie'])
        self.assertEqual(kyc.status, 'pending')  # request_info never revokes

        service.decide(kyc, 'reject', actor_label='ops:a@wepl.app', reason='Blurred ID')
        kyc.refresh_from_db()
        self.assertEqual(kyc.status, 'rejected')
        self.assertEqual(kyc.rejection_reason, 'Blurred ID')

        # rejected → reject again is illegal
        with self.assertRaises(service.IllegalTransition):
            service.decide(kyc, 'reject', actor_label='x', reason='again')

    def test_customer_resubmit_reopens_a_rejected_case(self):
        kyc = _kyc()
        service.decide(kyc, 'reject', actor_label='x', reason='r')
        case = service.record_submission(kyc, kind='full_resubmit')
        self.assertEqual(case.state, VerificationCase.State.SUBMITTED)
        self.assertIsNone(case.closed_at)


class OpsDecisionEndpointTests(TestCase):
    """The console decision API drives the same chokepoint."""

    def setUp(self):
        self.kyc = _kyc(phone='+254700000009', id_number='99999999')
        self.staff = StaffAccount.objects.create(
            email='reviewer@wepl.app', full_name='Reviewer', is_superuser=True)
        self.staff.set_password('S3cure-pass!')
        self.staff.save()
        token = issue_staff_token(self.staff)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def _decide(self, body):
        return self.client.post(f'/api/ops/verification/{self.kyc.user_id}/decision/',
                                body, format='json')

    def test_approve_writes_case_event_and_returns_timeline(self):
        res = self._decide({'action': 'approve'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['status'], 'approved')
        self.assertEqual(res.data['case_state'], 'approved')
        types = [e['type'] for e in res.data['timeline']]
        self.assertIn('review.approved', types)
        ev = CaseEvent.objects.get(case__kyc=self.kyc, event_type='review.approved')
        self.assertEqual(ev.actor_staff_id, self.staff.pk)
        self.assertEqual(ev.actor_kind, 'staff')

    def test_double_approve_is_a_409_conflict(self):
        self.assertEqual(self._decide({'action': 'approve'}).status_code, 200)
        res = self._decide({'action': 'approve'})
        self.assertEqual(res.status_code, 409)

    def test_case_payload_includes_document_versions(self):
        service.record_submission(self.kyc, kind='initial')
        res = self.client.get(f'/api/ops/verification/{self.kyc.user_id}/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data['documents']['id_front']['versions']), 1)
        self.assertEqual(res.data['documents']['id_front']['versions'][0]['version'], 1)
