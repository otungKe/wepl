"""Inbound callback views consume normalised CallbackEvents (P1-04)."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.ledger.models import FinancialTransaction
from apps.ledger.writer import create_fin_transaction
from apps.mpesa.models import MpesaSTKRequest
from apps.payments.providers import registry
from apps.payments.providers.fake import FakeProvider

User = get_user_model()


class STKCallbackViewTests(APITestCase):
    URL = "/api/mpesa/stk/callback/"

    def setUp(self):
        registry.use_provider(FakeProvider())
        self.user = User.objects.create(phone_number="+254700000700")
        self.stk = MpesaSTKRequest.objects.create(
            user=self.user, payment_type="contribution",
            phone_number="254700000700", amount=Decimal("100"),
            checkout_request_id="ws_CO_1", merchant_request_id="m1",
        )

    def tearDown(self):
        registry.use_provider(None)

    def test_success_callback_marks_request_success(self):
        resp = self.client.post(self.URL, {
            "provider_ref": "ws_CO_1", "success": True, "receipt": "QABC123",
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        self.stk.refresh_from_db()
        self.assertEqual(self.stk.status, "SUCCESS")
        self.assertEqual(self.stk.mpesa_receipt, "QABC123")

    def test_failure_callback_marks_request_failed(self):
        resp = self.client.post(self.URL, {
            "provider_ref": "ws_CO_1", "success": False,
            "code": "1032", "result_desc": "cancelled by user",
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        self.stk.refresh_from_db()
        self.assertEqual(self.stk.status, "FAILED")
        self.assertEqual(self.stk.result_code, 1032)

    def test_duplicate_callback_is_idempotent(self):
        MpesaSTKRequest.objects.filter(pk=self.stk.pk).update(status="SUCCESS")
        resp = self.client.post(self.URL, {
            "provider_ref": "ws_CO_1", "success": True, "receipt": "X",
        }, format="json")
        self.assertEqual(resp.status_code, 200)  # no-op, still accepted

    def test_unknown_ref_is_accepted(self):
        resp = self.client.post(self.URL, {
            "provider_ref": "", "success": True,
        }, format="json")
        self.assertEqual(resp.status_code, 200)


class B2CResultViewTests(APITestCase):
    URL = "/api/mpesa/b2c/result/"

    def setUp(self):
        registry.use_provider(FakeProvider())
        self.user = User.objects.create(phone_number="+254700000701")
        self.ft, _ = create_fin_transaction(
            idempotency_key="ft-b2c-1", op_type=FinancialTransaction.OpType.DISBURSEMENT,
            amount=Decimal("500"), initiated_by=self.user, recipient_phone="254700000701",
            initial_state=FinancialTransaction.State.PROCESSING,
        )
        FinancialTransaction.objects.filter(pk=self.ft.pk).update(mpesa_conversation_id="AG_1")

    def tearDown(self):
        registry.use_provider(None)

    def test_success_marks_ft_success(self):
        resp = self.client.post(self.URL, {
            "provider_ref": "AG_1", "success": True, "receipt": "NLJ7RT61SV",
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        self.ft.refresh_from_db()
        self.assertEqual(self.ft.state, FinancialTransaction.State.SUCCESS)
        self.assertEqual(self.ft.mpesa_receipt, "NLJ7RT61SV")

    def test_failure_marks_ft_failed(self):
        resp = self.client.post(self.URL, {
            "provider_ref": "AG_1", "success": False, "code": "2001",
            "result_desc": "insufficient funds",
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        self.ft.refresh_from_db()
        self.assertEqual(self.ft.state, FinancialTransaction.State.FAILED)

    def test_unknown_conversation_is_accepted(self):
        resp = self.client.post(self.URL, {
            "provider_ref": "", "success": True,
        }, format="json")
        self.assertEqual(resp.status_code, 200)
