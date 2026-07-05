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
from .models import (
    CaseDocument, CaseEvent, CaseNote, OcrResult, RejectionReason, VerificationCase,
)

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


class CodedRejectionTests(TestCase):

    def test_catalogue_is_seeded(self):
        codes = set(RejectionReason.objects.values_list('code', flat=True))
        self.assertIn('DOC_UNREADABLE', codes)
        self.assertIn('OTHER', codes)

    def test_coded_rejection_shows_customer_the_vetted_message(self):
        kyc = _kyc(phone='+254700000021', id_number='21212121')
        service.decide(kyc, 'reject', actor_label='ops:a@wepl.app',
                       reason='internal: fonts look wrong', reason_code='DOC_INVALID')
        kyc.refresh_from_db()
        coded = RejectionReason.objects.get(code='DOC_INVALID')
        self.assertEqual(kyc.rejection_reason, coded.customer_message)
        ev = CaseEvent.objects.get(case__kyc=kyc, event_type='review.rejected')
        self.assertEqual(ev.payload['reason_code'], 'DOC_INVALID')
        self.assertEqual(ev.payload['reason'], 'internal: fonts look wrong')

    def test_other_code_falls_through_to_free_text(self):
        kyc = _kyc(phone='+254700000022', id_number='22222222')
        service.decide(kyc, 'reject', actor_label='x',
                       reason='Name order swapped on the form.', reason_code='OTHER')
        kyc.refresh_from_db()
        self.assertEqual(kyc.rejection_reason, 'Name order swapped on the form.')

    def test_unknown_code_is_rejected(self):
        kyc = _kyc(phone='+254700000023', id_number='23232323')
        with self.assertRaises(ValueError):
            service.decide(kyc, 'reject', actor_label='x', reason_code='NOPE')


class WorkingTheCaseTests(TestCase):

    def setUp(self):
        self.kyc = _kyc(phone='+254700000031', id_number='31313131')
        self.staff = StaffAccount.objects.create(
            email='analyst@wepl.app', full_name='Analyst', is_superuser=True)
        self.staff.set_password('S3cure-pass!')
        self.staff.save()

    def test_claim_and_release_are_evented(self):
        case = service.claim(self.kyc, staff=self.staff)
        self.assertEqual(case.assigned_to, self.staff)
        service.release(self.kyc, staff=self.staff)
        case.refresh_from_db()
        self.assertIsNone(case.assigned_to)
        types = list(CaseEvent.objects.filter(case=case)
                     .order_by('seq').values_list('event_type', flat=True))
        self.assertIn('case.assigned', types)
        self.assertIn('case.unassigned', types)

    def test_terminal_case_cannot_be_claimed(self):
        service.decide(self.kyc, 'approve', actor_label='x')
        with self.assertRaises(service.IllegalTransition):
            service.claim(self.kyc, staff=self.staff)

    def test_notes_are_append_only(self):
        note = service.add_note(self.kyc, body='ID looks fine; waiting on selfie.',
                                staff=self.staff)
        self.assertEqual(note.author_label, 'analyst@wepl.app')
        note.body = 'edited'
        with self.assertRaises(ValueError):
            note.save()

    def test_check_persists_ocr_result_linked_to_document_version(self):
        service.record_submission(self.kyc, kind='initial')
        service.record_check(self.kyc, provider='fake', state='manual_review',
                             detail={'ocr': {'engine': 'tesseract', 'detected': True,
                                             'id_number_match': False, 'mismatch': True}})
        row = OcrResult.objects.get(case__kyc=self.kyc)
        self.assertEqual(row.engine, 'tesseract')
        self.assertTrue(row.detected)
        self.assertFalse(row.id_number_match)
        self.assertEqual(row.document.doc_type, 'id_front')
        self.assertEqual(row.document.version, 1)


class OpsWorkflowEndpointTests(TestCase):

    def setUp(self):
        self.kyc = _kyc(phone='+254700000041', id_number='41414141')
        self.staff = StaffAccount.objects.create(
            email='ops@wepl.app', full_name='Ops', is_superuser=True)
        self.staff.set_password('S3cure-pass!')
        self.staff.save()
        token = issue_staff_token(self.staff)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        self.base = f'/api/ops/verification/{self.kyc.user_id}'

    def test_note_endpoint(self):
        res = self.client.post(f'{self.base}/notes/', {'body': 'Checked against register.'},
                               format='json')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['notes'][0]['body'], 'Checked against register.')
        self.assertEqual(res.data['notes'][0]['author'], 'ops@wepl.app')
        self.assertEqual(self.client.post(f'{self.base}/notes/', {'body': '  '},
                                          format='json').status_code, 400)

    def test_claim_release_endpoint_and_queue_assignee(self):
        res = self.client.post(f'{self.base}/assign/', {'action': 'claim'}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['assignee'], 'ops@wepl.app')

        q = self.client.get('/api/ops/verification/queue/', {'assigned': 'me'})
        self.assertEqual(q.data['count'], 1)
        self.assertEqual(q.data['results'][0]['assignee'], 'ops@wepl.app')

        res = self.client.post(f'{self.base}/assign/', {'action': 'release'}, format='json')
        self.assertIsNone(res.data['assignee'])
        q = self.client.get('/api/ops/verification/queue/', {'assigned': 'nobody'})
        self.assertEqual(q.data['count'], 1)

    def test_coded_reject_via_api(self):
        res = self.client.post(f'{self.base}/decision/',
                               {'action': 'reject', 'reason_code': 'DOC_UNREADABLE'},
                               format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['status'], 'rejected')
        self.kyc.refresh_from_db()
        self.assertIn('not clear enough', self.kyc.rejection_reason)
        bad = self.client.post(f'{self.base}/decision/',
                               {'action': 'reject', 'reason_code': 'BOGUS'}, format='json')
        self.assertEqual(bad.status_code, 400)

    def test_case_payload_lists_rejection_codes(self):
        res = self.client.get(f'{self.base}/')
        codes = [r['code'] for r in res.data['rejection_reasons']]
        self.assertIn('DOC_UNREADABLE', codes)
        self.assertEqual(codes[-1], 'OTHER')  # sorted, catch-all last
