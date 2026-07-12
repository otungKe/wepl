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

    def test_lost_race_transition_does_not_apply_its_metadata(self):
        # The optimistic status guard serialises transitions: the loser's metadata
        # never merges in, so the documented read-modify-write merge can't lose the
        # winner's keys. (Two workers, same PENDING base.)
        from apps.core.exceptions import TransitionError
        winner = self._pending(provider_ref="M", idempotency_key="a")
        loser = PaymentIntent.objects.get(pk=winner.pk)   # a second stale handle
        winner.transition_to(S.SUCCEEDED, metadata={"foo": 1})
        with self.assertRaises(TransitionError):
            loser.transition_to(S.FAILED, metadata={"bar": 2})   # rows==0, raises
        fresh = PaymentIntent.objects.get(pk=winner.pk)
        self.assertEqual(fresh.status, S.SUCCEEDED)
        self.assertEqual(fresh.metadata, {"foo": 1})   # "bar" never landed

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

    def test_provider_event_correlates_to_intent(self):
        # An event recorded by provider_ref links to its intent automatically —
        # the log is per-intent for investigation/audit.
        i = self._pending(provider_ref="CORR", idempotency_key="a")
        ev = PaymentService.record_provider_event(
            provider="mpesa", event_type="payout_result", payload={"x": 1},
            provider_ref="CORR")
        self.assertEqual(ev.payment_intent_id, i.id)

    def test_provider_event_bulk_mutation_blocked(self):
        from apps.core.exceptions import TransitionError
        from .models import ProviderEvent
        PaymentService.record_provider_event(
            provider="mpesa", event_type="payout_result", payload={}, provider_ref="B1")
        qs = ProviderEvent.objects.filter(provider_ref="B1")
        for call in (lambda: qs.update(event_type="x"),
                     lambda: qs.delete(),
                     lambda: ProviderEvent.objects.bulk_update([], ["event_type"])):
            with self.assertRaises(TransitionError):
                call()

    def test_intent_delete_still_nulls_event_fk(self):
        # The append-only queryset guard must not break FK SET_NULL cascades.
        from .models import ProviderEvent
        i = self._pending(provider_ref="CASC", idempotency_key="a")
        ev = PaymentService.record_provider_event(
            provider="mpesa", event_type="payout_result", payload={}, provider_ref="CASC")
        i.delete()
        ev.refresh_from_db()
        self.assertIsNone(ev.payment_intent_id)

    def test_future_completion_time_clamped(self):
        from datetime import timedelta
        from django.utils import timezone
        i = self._pending(provider_ref="FUT", idempotency_key="a")
        future = timezone.now() + timedelta(days=3650)
        i.transition_to(S.SUCCEEDED, completed_at=future)
        i.refresh_from_db()
        self.assertLessEqual(i.provider_completed_at, timezone.now())

    def test_is_terminal(self):
        i = self._pending(provider_ref="T", idempotency_key="a")
        self.assertFalse(i.is_terminal)             # PENDING → {SUCCEEDED, FAILED}
        i.transition_to(S.SUCCEEDED)
        self.assertFalse(i.is_terminal)             # SUCCEEDED → {REVERSED}
        i.transition_to(S.REVERSED)
        self.assertTrue(i.is_terminal)              # REVERSED → {}

    def test_drift_resolve_is_idempotent(self):
        i = self._pending(provider_ref="D", idempotency_key="a")
        d = ReconciliationDrift.objects.create(
            kind="amount_mismatch", subject_type="payment_intent", subject_id=str(i.id))
        d.resolve()
        first = d.resolved_at
        self.assertIsNotNone(first)
        d.resolve()   # no-op — not reopened or re-stamped
        self.assertEqual(d.resolved_at, first)


class ReconciliationOwnershipTests(TestCase):
    """PaymentService orchestrates lifecycle only; the duplicate-receipt
    consistency check is owned by the reconciliation subsystem (which resolve
    delegates to)."""

    def test_duplicate_receipt_owned_by_reconciliation(self):
        from . import reconciliation
        a = PaymentService.record_initiation(
            provider="mpesa", direction=D.COLLECTION, amount=Decimal("1"),
            idempotency_key="a", provider_ref="R1")
        a.transition_to(S.SUCCEEDED, receipt="DUP1")
        b = PaymentService.record_initiation(
            provider="mpesa", direction=D.COLLECTION, amount=Decimal("1"),
            idempotency_key="b", provider_ref="R2")
        # The reconciliation-owned check flags the dup and tells the caller to skip it.
        self.assertTrue(reconciliation.note_duplicate_receipt(b, "DUP1"))
        self.assertFalse(reconciliation.note_duplicate_receipt(b, "FRESH"))
        self.assertTrue(ReconciliationDrift.objects.filter(
            kind="duplicate_receipt", subject_id=str(b.id)).exists())


class OperatorRecoverySettlesIntentTests(TestCase):
    """PaymentOpsService heals through the SAME door callbacks use — operator
    recovery settles the linked PaymentIntent, leaving no intent↔FT drift."""

    def setUp(self):
        from apps.payments.providers import registry
        from apps.payments.providers.fake import FakeProvider
        self.fake = FakeProvider()
        registry.use_provider(self.fake)
        self.addCleanup(registry.use_provider, None)

    def _payout(self, state, conv="CONV1"):
        ft = make_ft(state=state, mpesa_conversation_id=conv)
        PaymentService.record_initiation(
            provider=self.fake.name, direction=D.PAYOUT, amount=ft.amount,
            idempotency_key=f"pi-{ft.id}", provider_ref=conv, financial_transaction=ft)
        return ft

    def test_requery_success_settles_intent(self):
        from apps.payments.ops import PaymentOpsService
        ft = self._payout(FinancialTransaction.State.PROCESSING)
        self.fake.set_status("CONV1", "success")
        PaymentOpsService.requery(ft, actor_label="tester")
        intent = PaymentIntent.objects.get(provider_ref="CONV1")
        self.assertEqual(intent.status, S.SUCCEEDED)   # settled via the shared door
        # And reconciliation sees no intent/FT mismatch.
        self.assertNotIn("intent_ft_mismatch", reconcile_payments())

    def test_mark_failed_settles_intent(self):
        from apps.payments.ops import PaymentOpsService
        ft = self._payout(FinancialTransaction.State.PROCESSING, conv="CONV2")
        self.fake.set_status("CONV2", "failed")
        PaymentOpsService.mark_failed(ft, reason="rail confirmed failure", actor_label="t")
        self.assertEqual(PaymentIntent.objects.get(provider_ref="CONV2").status, S.FAILED)
