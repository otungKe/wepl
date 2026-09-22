"""The rail app asks the domain what a settled payment means; it never imports it.

If this seam is unwired, nothing raises at import time — money simply stops being
credited. So these tests assert the wiring itself, not only the routing.
"""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.mpesa import settlement
from apps.mpesa.models import MpesaC2BTransaction, MpesaSTKRequest
from apps.mpesa.services import MpesaService
from apps.mpesa.tasks import process_stk_sync

User = get_user_model()


class RegisteredAtStartupTests(TestCase):
    """apps.contributions fills both slots from its AppConfig.ready()."""

    def test_collection_handler_is_registered(self):
        self.assertIsNotNone(settlement._collection_settled)

    def test_paybill_resolver_is_registered(self):
        self.assertIsNotNone(settlement._paybill_resolver)

    def test_collection_handler_routes_to_the_domain(self):
        with patch("apps.contributions.settlement.on_collection_settled") as domain:
            settlement.run_collection_settled(payment_type="contribution", user=None,
                                              amount=Decimal("1"))
        domain.assert_called_once()

    def test_paybill_resolver_routes_to_the_domain(self):
        with patch("apps.contributions.services.ContributionService."
                   "credit_paybill_payin", return_value={"reconciled": False,
                                                         "reason": "x",
                                                         "contribution_id": None,
                                                         "user_id": None}) as domain:
            settlement.resolve_paybill_payin(reference="WEPL-1", phone="254700000001",
                                             amount=Decimal("1"), receipt="R",
                                             payer_name="")
        domain.assert_called_once()


class UnregisteredTests(TestCase):
    """The two slots fail differently on purpose."""

    def setUp(self):
        self._collection = settlement._collection_settled
        self._paybill = settlement._paybill_resolver
        settlement._collection_settled = None
        settlement._paybill_resolver = None

    def tearDown(self):
        settlement._collection_settled = self._collection
        settlement._paybill_resolver = self._paybill

    def test_settled_collection_with_no_handler_raises(self):
        """A settled STK payment with nowhere to go must fail loudly, so the
        Celery task retries rather than silently dropping a credit."""
        with self.assertRaises(RuntimeError):
            settlement.run_collection_settled(payment_type="contribution", user=None,
                                              amount=Decimal("1"))

    def test_paybill_with_no_resolver_is_recorded_unreconciled(self):
        """The deposit is already banked — leave the row for review, don't raise."""
        result = settlement.resolve_paybill_payin(
            reference="WEPL-1", phone="254700000001", amount=Decimal("1"),
            receipt="R", payer_name="")
        self.assertFalse(result["reconciled"])
        self.assertIsNone(result["contribution_id"])


class ReconcileC2BThroughTheSeamTests(TestCase):
    """reconcile_c2b stamps its own row from whatever the domain answers."""

    def setUp(self):
        self.user = User.objects.create(phone_number="254700000401")
        self.tx = MpesaC2BTransaction.objects.create(
            phone_number="254700000401", amount=Decimal("500"),
            mpesa_receipt="RCT_SEAM_1", transaction_date="2026-05-28T12:00:00Z",
            bill_ref_number="WEPL-7",
        )

    def _answer(self, **over):
        base = {"reconciled": True, "reason": "ok",
                "contribution_id": None, "user_id": self.user.id}
        base.update(over)
        return base

    def test_unresolved_deposit_leaves_the_row_alone(self):
        with patch.object(settlement, "_paybill_resolver",
                          lambda **kw: self._answer(reconciled=False, user_id=None)):
            self.assertFalse(MpesaService.reconcile_c2b(self.tx))
        self.tx.refresh_from_db()
        self.assertFalse(self.tx.is_reconciled)
        self.assertIsNone(self.tx.user_id)

    def test_the_domain_answer_is_passed_the_rail_fields(self):
        seen = {}

        def _resolver(**kw):
            seen.update(kw)
            return self._answer(reconciled=False, user_id=None)

        with patch.object(settlement, "_paybill_resolver", _resolver):
            MpesaService.reconcile_c2b(self.tx)
        self.assertEqual(seen["reference"], "WEPL-7")
        self.assertEqual(seen["phone"], "254700000401")
        self.assertEqual(seen["receipt"], "RCT_SEAM_1")


class SyncProcessingFallsBackTests(TestCase):
    """A raising domain handler must still reach the Celery retry queue —
    the behaviour the inline call had before the seam existed."""

    def setUp(self):
        self.user = User.objects.create(phone_number="254700000402")
        self.stk = MpesaSTKRequest.objects.create(
            user=self.user, payment_type="contribution",
            phone_number="254700000402", amount=Decimal("100"),
            checkout_request_id="ws_CO_SEAM", merchant_request_id="m1",
            status="SUCCESS", mpesa_receipt="RCT_SEAM_2",
        )

    def test_handler_failure_schedules_the_retry(self):
        def _boom(**kw):
            raise ValueError("domain blew up")

        with patch.object(settlement, "_collection_settled", _boom), \
                patch("apps.mpesa.tasks.enqueue_stk_processing") as retry:
            process_stk_sync(self.stk.id)
        retry.assert_called_once_with(self.stk.id)

    def test_success_does_not_schedule_a_retry(self):
        with patch.object(settlement, "_collection_settled", lambda **kw: None), \
                patch("apps.mpesa.tasks.enqueue_stk_processing") as retry:
            process_stk_sync(self.stk.id)
        retry.assert_not_called()
