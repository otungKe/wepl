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
                                        success=False, failure_code="1032",
                                        failure_message="insufficient funds")
        self.assertEqual(intent.status, S.FAILED)
        self.assertEqual(intent.failure_code, "1032")
        self.assertEqual(intent.failure_message, "insufficient funds")

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

    def test_amount_mismatch_flagged(self):
        ft = make_ft(state=FinancialTransaction.State.SUCCESS)   # amount 500
        PaymentService.record_initiation(
            provider="mpesa", direction=D.PAYOUT, amount=Decimal("450"),
            idempotency_key="am", provider_ref="AM1", financial_transaction=ft)
        counts = reconcile_payments()
        self.assertEqual(counts.get("amount_mismatch"), 1)


class PaymentIntentHardeningTests(TestCase):
    """Post-MVP hardening: uniqueness, lifecycle timestamps, encapsulated
    transitions, structured failure, provider-event history."""

    def _pending(self, **kw):
        base = dict(provider="mpesa", direction=D.COLLECTION, amount=Decimal("100"),
                    idempotency_key=f"idem-{kw.get('provider_ref', 'x')}")
        base.update(kw)
        return PaymentService.record_initiation(**base)

    # ── Uniqueness ─────────────────────────────────────────────────────────────
    def test_provider_ref_unique_per_provider(self):
        from django.db import IntegrityError, transaction
        self._pending(provider_ref="DUP", idempotency_key="a")
        with self.assertRaises(IntegrityError), transaction.atomic():
            PaymentIntent.objects.create(
                provider="mpesa", direction=D.COLLECTION, amount=Decimal("1"),
                idempotency_key="b", provider_ref="DUP")

    def test_blank_provider_ref_allowed_many(self):
        # Blank refs must not collide during initiation.
        self._pending(provider_ref="", idempotency_key="a")
        self._pending(provider_ref="", idempotency_key="b")
        self.assertEqual(PaymentIntent.objects.filter(provider_ref="").count(), 2)

    def test_receipt_unique_when_populated(self):
        from django.db import IntegrityError, transaction
        i = self._pending(provider_ref="R1", idempotency_key="a")
        i.transition_to(S.SUCCEEDED, receipt="RCPT9")
        j = self._pending(provider_ref="R2", idempotency_key="b")
        with self.assertRaises(IntegrityError), transaction.atomic():
            j.transition_to(S.SUCCEEDED, receipt="RCPT9")

    def test_duplicate_receipt_settles_without_it_and_flags_drift(self):
        self._pending(provider_ref="R1", idempotency_key="a").transition_to(
            S.SUCCEEDED, receipt="RCPTDUP")
        self._pending(provider_ref="R2", idempotency_key="b")
        # A second intent whose callback carries the same receipt still settles,
        # loses the duplicate receipt, and raises a drift.
        got = PaymentService.resolve(provider="mpesa", provider_ref="R2",
                                     success=True, receipt="RCPTDUP")
        self.assertEqual(got.status, S.SUCCEEDED)
        self.assertEqual(got.receipt, "")
        self.assertTrue(ReconciliationDrift.objects.filter(
            kind="duplicate_receipt", subject_id=str(got.id), resolved_at__isnull=True).exists())

    # ── Lifecycle timestamps ────────────────────────────────────────────────────
    def test_lifecycle_timestamps(self):
        i = self._pending(provider_ref="TS", idempotency_key="a")
        self.assertIsNotNone(i.initiated_at)
        self.assertIsNone(i.callback_received_at)
        self.assertIsNone(i.provider_completed_at)
        got = PaymentService.resolve(provider="mpesa", provider_ref="TS", success=True,
                                     receipt="RC1")
        self.assertIsNotNone(got.callback_received_at)   # callback landed
        self.assertIsNotNone(got.provider_completed_at)  # provider reached terminal

    # ── Encapsulated transitions ────────────────────────────────────────────────
    def test_direct_status_assignment_blocked(self):
        from apps.core.exceptions import TransitionError
        i = self._pending(provider_ref="G", idempotency_key="a")
        i.status = S.SUCCEEDED
        with self.assertRaises(TransitionError):
            i.save()

    def test_illegal_transition_raises_on_model(self):
        from apps.core.exceptions import TransitionError
        i = self._pending(provider_ref="G", idempotency_key="a")
        i.transition_to(S.FAILED)
        with self.assertRaises(TransitionError):
            i.transition_to(S.REVERSED)   # FAILED has no outgoing edges

    def test_concurrent_settle_loses_race(self):
        from apps.core.exceptions import TransitionError
        i = self._pending(provider_ref="RACE", idempotency_key="a")
        # Simulate another worker settling first (DB row advances under us).
        PaymentIntent.objects.filter(pk=i.pk).update(status=S.SUCCEEDED)
        with self.assertRaises(TransitionError):
            i.transition_to(S.FAILED)   # optimistic UPDATE matches 0 rows

    # ── ProviderEvent history ───────────────────────────────────────────────────
    def test_provider_event_is_append_only(self):
        from apps.core.exceptions import TransitionError
        from .models import ProviderEvent
        ev = PaymentService.record_provider_event(
            provider="mpesa", event_type="payout_result", payload={"ResultCode": 0},
            provider_ref="X1", signature_verified=True)
        self.assertIsNotNone(ev)
        ev.event_type = "changed"
        with self.assertRaises(TransitionError):
            ev.save()
        with self.assertRaises(TransitionError):
            ev.delete()

    def test_provider_event_dedups_on_event_id(self):
        from .models import ProviderEvent
        a = PaymentService.record_provider_event(
            provider="mpesa", event_type="payout_result", payload={},
            provider_event_id="EVT-1")
        b = PaymentService.record_provider_event(
            provider="mpesa", event_type="payout_result", payload={},
            provider_event_id="EVT-1")
        self.assertIsNotNone(a)
        self.assertIsNone(b)   # re-delivery dropped
        self.assertEqual(ProviderEvent.objects.filter(provider_event_id="EVT-1").count(), 1)
