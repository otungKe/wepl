"""Tests for the PaymentProvider abstraction (Phase 1 / ADR-0005)."""
from decimal import Decimal
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.ledger.money import Money
from apps.payments.providers import (
    CallbackEvent, CollectionResult, PayoutResult, PaymentProvider,
)
from apps.payments.providers.fake import FakeProvider
from apps.payments.providers.mpesa import MpesaProvider
from apps.payments.providers import registry


class FakeProviderContractTests(SimpleTestCase):
    """The fake satisfies the full contract with no network."""

    def setUp(self):
        self.p = FakeProvider()

    def test_is_a_payment_provider(self):
        self.assertIsInstance(self.p, PaymentProvider)

    def test_collection_and_payout_lifecycle(self):
        col = self.p.initiate_collection(
            phone="+254700000001", amount=Money("100"),
            reference="WEPL-1", description="contribution")
        self.assertIsInstance(col, CollectionResult)
        self.assertTrue(col.accepted)
        self.assertEqual(self.p.collections[0]['amount'], Money("100"))

        pay = self.p.initiate_payout(
            phone="+254700000001", amount=Money("50"),
            reference="payout-1", remarks="disbursement")
        self.assertIsInstance(pay, PayoutResult)
        self.assertTrue(pay.accepted)

        ev = self.p.make_collection_callback(col.provider_ref, amount=Decimal("100"))
        self.assertTrue(ev.success)
        self.assertEqual(ev.provider_ref, col.provider_ref)
        self.assertEqual(ev.receipt, "FAKE-RCPT")

    def test_rejecting_fake(self):
        p = FakeProvider(accept=False)
        self.assertFalse(p.initiate_collection(
            phone="x", amount=Money("1"), reference="r", description="d").accepted)


class MpesaProviderTests(SimpleTestCase):
    """All Daraja wire details stay inside the adapter; results are normalised."""

    def setUp(self):
        self.p = MpesaProvider()

    def test_initiate_collection_normalises_response(self):
        fake_resp = {"ResponseCode": "0", "CheckoutRequestID": "ws_CO_123"}
        with patch("apps.payments.providers.mpesa.MpesaService.stk_push",
                   return_value=fake_resp) as m:
            res = self.p.initiate_collection(
                phone="+254700000001", amount=Money("100.50"),
                reference="WEPL-1", description="contribution")
        self.assertTrue(res.accepted)
        self.assertEqual(res.provider_ref, "ws_CO_123")
        # M-Pesa transacts whole shillings — Money is rounded to an int amount.
        self.assertEqual(m.call_args.kwargs["amount"], 100)

    def test_initiate_payout_normalises_response(self):
        fake_resp = {"ResponseCode": "0", "ConversationID": "AG_123"}
        with patch("apps.payments.providers.mpesa.MpesaService.b2c_payment",
                   return_value=fake_resp):
            res = self.p.initiate_payout(
                phone="+254700000001", amount=Money("75"),
                reference="payout-1", remarks="disbursement")
        self.assertTrue(res.accepted)
        self.assertEqual(res.provider_ref, "AG_123")

    def test_parse_stk_success_callback(self):
        payload = {"Body": {"stkCallback": {
            "CheckoutRequestID": "ws_CO_1",
            "ResultCode": 0, "ResultDesc": "ok",
            "CallbackMetadata": {"Item": [
                {"Name": "Amount", "Value": 100},
                {"Name": "MpesaReceiptNumber", "Value": "QABC123"},
                {"Name": "PhoneNumber", "Value": 254700000001},
            ]},
        }}}
        ev = self.p.parse_callback(payload, kind="collection")
        self.assertIsInstance(ev, CallbackEvent)
        self.assertTrue(ev.success)
        self.assertEqual(ev.provider_ref, "ws_CO_1")
        self.assertEqual(ev.receipt, "QABC123")
        self.assertEqual(ev.amount, 100)

    def test_parse_stk_failure_callback(self):
        payload = {"Body": {"stkCallback": {
            "CheckoutRequestID": "ws_CO_2", "ResultCode": 1032,
            "ResultDesc": "cancelled",
        }}}
        ev = self.p.parse_callback(payload, kind="collection")
        self.assertFalse(ev.success)
        self.assertIsNone(ev.receipt)
        self.assertEqual(ev.result_desc, "cancelled")

    def test_query_status_maps_result_code(self):
        cases = [({"ResultCode": "0"}, "success"),
                 ({"ResultCode": "1032"}, "failed"),
                 ({}, "pending")]
        for resp, expected in cases:
            with patch("apps.payments.providers.mpesa.MpesaService.query_stk_status",
                       return_value=resp):
                self.assertEqual(self.p.query_status(provider_ref="ws_CO_1").state, expected)

    def test_parse_b2c_success_result(self):
        payload = {"Result": {
            "ConversationID": "AG_1", "ResultCode": 0, "ResultDesc": "done",
            "ResultParameters": {"ResultParameter": [
                {"Key": "TransactionReceipt", "Value": "NLJ7RT61SV"},
            ]},
        }}
        ev = self.p.parse_callback(payload, kind="payout")
        self.assertTrue(ev.success)
        self.assertEqual(ev.provider_ref, "AG_1")
        self.assertEqual(ev.receipt, "NLJ7RT61SV")


class RegistryTests(SimpleTestCase):
    def tearDown(self):
        registry.use_provider(None)

    def test_override_wins(self):
        fake = FakeProvider()
        registry.use_provider(fake)
        self.assertIs(registry.get_provider(), fake)

    def test_named_selection(self):
        registry.use_provider(None)
        with self.settings(PAYMENT_PROVIDER="fake"):
            self.assertIsInstance(registry.get_provider(), FakeProvider)
        with self.settings(PAYMENT_PROVIDER="mpesa"):
            self.assertIsInstance(registry.get_provider(), MpesaProvider)
