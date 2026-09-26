"""Closing an account and exporting its data (boundary audit step 8)."""
import datetime
import io

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.core import lifecycle as core_lifecycle
from apps.ledger import coa
from apps.ledger import posting_map as pm
from apps.ledger.money import Money
from apps.ledger.posting import post_journal
from apps.payments.models import PaymentMethod
from apps.users.auth import STAGE_ACTIVE, issue_tokens
from apps.users.lifecycle import AccountCannotClose, close_account
from apps.verification import service as verification
from apps.verification.lifecycle import erase_identity_evidence
from apps.verification.models import CaseDocument, CaseEvent, KYCProfile
from apps.verification.tasks import erase_expired_identity_evidence

User = get_user_model()


def _png(name):
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (8, 8), 'white').save(buf, format='PNG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/png')


def _customer(phone='+254700000501'):
    user = User.objects.create_user(phone_number=phone, is_phone_verified=True)
    kyc = KYCProfile.objects.create(
        user=user, given_names='Wanjiku', surname='Kamau', id_number='22223333',
        date_of_birth=datetime.date(1990, 1, 1), email='w@example.com', kra_pin='A123456789Z',
        county='Nairobi', physical_address='Moi Ave 1', occupation='Trader',
        source_of_income='business', expected_monthly_income='under_250k',
        id_front=_png('front.png'), selfie=_png('selfie.png'), status='pending',
    )
    verification.record_submission(kyc, kind='initial')
    PaymentMethod.objects.create(user=user, kind=PaymentMethod.Kind.MPESA,
                                 mpesa_phone='254712345678', is_default=True)
    return user, kyc


class LifecycleRegistrationTests(TestCase):

    def test_every_context_that_holds_customer_data_is_registered(self):
        # A lost registration fails silently: closure would skip that context's
        # checks and leave its data behind.
        self.assertEqual(
            {p.name for p in core_lifecycle.participants()},
            {"verification", "payments", "communities", "contributions"},
        )


class CloseAccountTests(TestCase):

    def test_closure_erases_personal_data_and_keeps_identity_evidence(self):
        user, kyc = _customer()
        with self.captureOnCommitCallbacks(execute=True):
            close_account(user)

        user.refresh_from_db()
        kyc.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertEqual(user.name, '[deleted]')
        self.assertTrue(user.phone_number.startswith('+0000'))
        self.assertFalse(PaymentMethod.objects.filter(user=user).exists())
        # Not identity evidence: gone at once.
        self.assertEqual(kyc.email, '')
        # Identity evidence: kept for the retention period, stamped on the case.
        self.assertEqual(kyc.id_number, '22223333')
        self.assertTrue(kyc.id_front)
        self.assertEqual(kyc.evidence_retain_until.year, datetime.date.today().year + 7)
        self.assertTrue(CaseEvent.objects.filter(case__user=user, event_type='account.closed').exists())
        self.assertTrue(AuditEvent.objects.filter(action='account.closed', target_id=str(user.id)).exists())

    def test_money_held_in_a_group_blocks_closure(self):
        user, _ = _customer()
        post_journal(idempotency_key='lifecycle-c1', op_type=pm.Op.CONTRIBUTION,
                     lines=pm.contribution_lines(member=user, fund_type='contribution',
                                                 fund_id=1, gross=Money('500')))
        with self.assertRaises(AccountCannotClose) as ctx:
            close_account(user)
        self.assertIn('hold money in a group', ctx.exception.reasons[0])
        user.refresh_from_db()
        self.assertTrue(user.is_active)

    def test_a_failing_context_rolls_the_whole_closure_back(self):
        user, kyc = _customer()

        def boom(u):
            raise RuntimeError('storage down')
        core_lifecycle.register('zz-test', erase=boom)
        try:
            with self.assertRaises(RuntimeError):
                close_account(user)
        finally:
            core_lifecycle._participants.pop('zz-test')
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertTrue(PaymentMethod.objects.filter(user=user).exists())

    def test_endpoint_returns_every_reason(self):
        user, _ = _customer()
        core_lifecycle.register('zz-test', blockers=lambda u: ['first', 'second'])
        try:
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(user, STAGE_ACTIVE)['access']}")
            r = client.delete('/api/users/account/')
        finally:
            core_lifecycle._participants.pop('zz-test')
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data['reasons'], ['first', 'second'])


class IdentityEvidenceErasureTests(TestCase):

    def test_sweep_erases_evidence_once_retention_has_passed(self):
        user, kyc = _customer()
        close_account(user)
        KYCProfile.objects.filter(pk=kyc.pk).update(
            evidence_retain_until=datetime.date.today() - datetime.timedelta(days=1))
        storage, name = kyc.id_front.storage, kyc.id_front.name

        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(erase_expired_identity_evidence(), 1)

        kyc.refresh_from_db()
        self.assertEqual(kyc.id_number, f'DELETED-{user.id}')
        self.assertEqual(kyc.kra_pin, '')
        self.assertFalse(kyc.id_front)
        self.assertIsNone(kyc.evidence_retain_until)
        self.assertFalse(CaseDocument.objects.filter(case__user=user).exclude(file='').exists())
        self.assertFalse(storage.exists(name))
        self.assertTrue(CaseEvent.objects.filter(case__user=user, event_type='evidence.erased').exists())

    def test_sweep_leaves_evidence_inside_retention(self):
        user, kyc = _customer()
        close_account(user)
        self.assertEqual(erase_expired_identity_evidence(), 0)
        kyc.refresh_from_db()
        self.assertEqual(kyc.id_number, '22223333')

    def test_erase_is_callable_directly(self):
        user, kyc = _customer()
        erase_identity_evidence(kyc)
        kyc.refresh_from_db()
        self.assertEqual(kyc.surname, '[deleted]')
