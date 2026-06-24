"""Payment aggregate + reconciliation tests (ADR-0014)."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.ledger.models import FinancialTransaction

from .models import PaymentIntent, ReconciliationDrift
from .reconciliation import reconcile_payments
from .services import PaymentService

User = get_user_model()
D = PaymentIntent.Direction
S = PaymentIntent.Status


def make_user(phone="254700000001"):
    u = User.objects.create(phone_number=phone)
    u.set_pin("123456")
    return u


_ft_seq = 0


def make_ft(state=FinancialTransaction.State.PROCESSING, **kw):
    global _ft_seq
    _ft_seq += 1
    return FinancialTransaction.objects.create(
        op_type=FinancialTransaction.OpType.DISBURSEMENT,
        state=state, amount=Decimal("500.00"),
        initiated_by=kw.pop("initiated_by", None) or make_user(f"2547009{_ft_seq:05d}"),
        idempotency_key=kw.pop("idempotency_key", f"ft-{_ft_seq}"),
        **kw,
    )


class PaymentServiceTests(TestCase):

    def setUp(self):
        self.user = make_user()

    def test_record_initiation_is_idempotent(self):
        kw = dict(provider="mpesa", direction=D.COLLECTION, amount=Decimal("100"),
                  idempotency_key="pi-collect-XYZ", provider_ref="XYZ")
        a = PaymentService.record_initiation(**kw)
        b = PaymentService.record_initiation(**kw)
        self.assertEqual(a.id, b.id)
        self.assertEqual(PaymentIntent.objects.count(), 1)
        self.assertEqual(a.status, S.PENDING)

    def test_resolve_success(self):
        PaymentService.record_initiation(
            provider="mpesa", direction=D.COLLECTION, amount=Decimal("100"),
            idempotency_key="k1", provider_ref="REF1")
        intent = PaymentService.resolve(provider="mpesa", provider_ref="REF1",
                                        success=True, receipt="QHX123")
        self.assertEqual(intent.status, S.SUCCEEDED)
        self.assertEqual(intent.receipt, "QHX123")

    def test_resolve_failure(self):
        PaymentService.record_initiation(
            provider="mpesa", direction=D.PAYOUT, amount=Decimal("100"),
            idempotency_key="k2", provider_ref="REF2")
        intent = PaymentService.resolve(provider="mpesa", provider_ref="REF2",
                                        success=False, failure_reason="insufficient funds")
        self.assertEqual(intent.status, S.FAILED)

    def test_resolve_is_idempotent_no_double_settle(self):
        PaymentService.record_initiation(
            provider="mpesa", direction=D.COLLECTION, amount=Decimal("100"),
            idempotency_key="k3", provider_ref="REF3")
        PaymentService.resolve(provider="mpesa", provider_ref="REF3", success=True)
        # second callback (duplicate) is a no-op — terminal intent untouched
        again = PaymentService.resolve(provider="mpesa", provider_ref="REF3", success=False)
        self.assertIsNone(again)
        self.assertEqual(
            PaymentIntent.objects.get(provider_ref="REF3").status, S.SUCCEEDED)

    def test_resolve_missing_ref_is_noop(self):
        self.assertIsNone(PaymentService.resolve(provider="mpesa", provider_ref="nope", success=True))

    def test_illegal_transition_blocked(self):
        i = PaymentService.record_initiation(
            provider="mpesa", direction=D.PAYOUT, amount=Decimal("100"),
            idempotency_key="k4", provider_ref="REF4")
        PaymentService.resolve(provider="mpesa", provider_ref="REF4", success=False)  # FAILED
        i.refresh_from_db()
        PaymentService.mark_reversed(i)   # FAILED → REVERSED is illegal → no-op
        i.refresh_from_db()
        self.assertEqual(i.status, S.FAILED)


class ReconciliationTests(TestCase):

    def test_stuck_pending_intent_flagged(self):
        i = PaymentService.record_initiation(
            provider="mpesa", direction=D.COLLECTION, amount=Decimal("100"),
            idempotency_key="k", provider_ref="OLD")
        PaymentIntent.objects.filter(pk=i.pk).update(
            created_at=timezone.now() - timedelta(hours=3))
        counts = reconcile_payments()
        self.assertEqual(counts.get("stuck_pending_intent"), 1)
        self.assertTrue(ReconciliationDrift.objects.filter(
            kind="stuck_pending_intent", subject_id=str(i.id), resolved_at__isnull=True).exists())

    def test_reconcile_is_idempotent_no_duplicate_drift(self):
        i = PaymentService.record_initiation(
            provider="mpesa", direction=D.COLLECTION, amount=Decimal("100"),
            idempotency_key="k", provider_ref="OLD")
        PaymentIntent.objects.filter(pk=i.pk).update(
            created_at=timezone.now() - timedelta(hours=3))
        reconcile_payments()
        reconcile_payments()
        self.assertEqual(ReconciliationDrift.objects.filter(
            kind="stuck_pending_intent", subject_id=str(i.id)).count(), 1)

    def test_intent_ft_mismatch_flagged(self):
        ft = make_ft(state=FinancialTransaction.State.FAILED)
        i = PaymentService.record_initiation(
            provider="mpesa", direction=D.PAYOUT, amount=Decimal("500"),
            idempotency_key="k", provider_ref="C1", financial_transaction=ft)
        PaymentService.resolve(provider="mpesa", provider_ref="C1", success=True)  # SUCCEEDED vs FT FAILED
        counts = reconcile_payments()
        self.assertEqual(counts.get("intent_ft_mismatch"), 1)

    def test_ft_stuck_processing_flagged(self):
        ft = make_ft(state=FinancialTransaction.State.PROCESSING)
        FinancialTransaction.objects.filter(pk=ft.pk).update(
            updated_at=timezone.now() - timedelta(hours=3))
        counts = reconcile_payments()
        self.assertEqual(counts.get("ft_stuck_processing"), 1)

    def test_clean_state_no_drift(self):
        # a recent pending intent + a fresh processing FT → nothing flagged
        PaymentService.record_initiation(
            provider="mpesa", direction=D.COLLECTION, amount=Decimal("100"),
            idempotency_key="k", provider_ref="NEW")
        self.assertEqual(reconcile_payments(), {})
