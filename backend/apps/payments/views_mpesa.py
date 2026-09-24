"""Daraja webhook endpoints, plus the STK status poll.

These are *payment* endpoints, not rail internals: each one turns a provider
callback into a ``PaymentIntent`` state change and, where money has actually
moved, into a ledger transition or a durable settlement event. They read the
M-Pesa rail records through ``apps.mpesa`` — the sanctioned direction, since
``apps.payments`` is the adapter layer and the rail client sits under it
(ADR-0005, ADR-0033).

They lived in ``apps/mpesa/views.py`` until the rail app was made a leaf. The
URLs they answer are registered with Safaricom and did not change; see
``config/urls_mpesa.py``.

Behaviour notes carried over from that file:
  - STKCallbackView: idempotent via atomic UPDATE WHERE status='PENDING' — a
    duplicate callback from Safaricom is a no-op (rows=0 → early return).
    All domain processing is deferred via on_commit — no silent exception
    swallowing in the HTTP handler.
  - B2CResultView: resolves FinancialTransaction by conversation_id, claims the
    transition and emits one durable settlement event (ADR-0028).
  - Callback views: SafaricomIPPermission applied (no-op when
    SAFARICOM_CALLBACK_IPS is empty, which production.py forbids against live
    Daraja).
"""
import logging
from datetime import datetime

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import TransitionError
from apps.mpesa import tasks as rail_tasks
from apps.mpesa.models import MpesaSTKRequest, MpesaC2BTransaction
from apps.mpesa.permissions import SafaricomIPPermission, allowlist_enforced
from apps.mpesa.services import MpesaService

logger = logging.getLogger(__name__)


class STKCallbackView(APIView):
    """
    Receives the async Daraja callback after a member completes/fails the STK prompt.

    Idempotency: uses UPDATE WHERE status='PENDING' to atomically claim the callback.
    If rows=0 the callback was already processed — return 200 immediately.

    Processing is deferred to on_commit so that transient failures (DB, downstream
    service) are retried rather than swallowed in the HTTP handler.
    """
    permission_classes = [SafaricomIPPermission]

    def post(self, request):
        from .providers.registry import get_provider
        event       = get_provider().parse_callback(request.data, kind='collection')
        checkout_id = event.provider_ref

        if not checkout_id:
            return Response({"ResultCode": 0, "ResultDesc": "Accepted"})

        # Settle the provider-agnostic payment aggregate (ADR-0014) — best-effort,
        # and durably record the raw callback for audit/replay first.
        try:
            from .services import PaymentService
            PaymentService.record_provider_event(
                provider=get_provider().name, event_type='collection_callback',
                payload=request.data, provider_ref=checkout_id,
                signature_verified=allowlist_enforced(),
            )
            PaymentService.resolve(
                provider=get_provider().name, provider_ref=checkout_id,
                success=event.success, receipt=event.receipt or '',
                failure_code=event.code or '', failure_message=event.result_desc or '',
            )
        except Exception:
            logger.exception("PaymentIntent resolve (collection) failed for %s", checkout_id)

        if event.success:
            # ── Success path ───────────────────────────────────────────────────
            receipt = event.receipt

            # Atomic claim + deferred processing.
            # on_commit ensures processing starts only after the UPDATE is
            # durably committed — no phantom work if the DB write is rolled back.
            with transaction.atomic():
                rows = MpesaSTKRequest.objects.filter(
                    checkout_request_id=checkout_id,
                    status='PENDING',
                ).update(status='SUCCESS', mpesa_receipt=receipt)

                if rows == 0:
                    logger.info(
                        "STKCallbackView: duplicate callback for %s — ignored", checkout_id
                    )
                    return Response({"ResultCode": 0, "ResultDesc": "Accepted"})

                try:
                    stk = MpesaSTKRequest.objects.get(checkout_request_id=checkout_id)
                except MpesaSTKRequest.DoesNotExist:
                    logger.error(
                        "STKCallbackView: STKRequest vanished after claim for %s", checkout_id
                    )
                    return Response({"ResultCode": 0, "ResultDesc": "Accepted"})

                stk_id = stk.id
                transaction.on_commit(
                    lambda: rail_tasks.process_stk_sync(stk_id)
                )

        else:
            # ── Failure path ───────────────────────────────────────────────────
            rows = MpesaSTKRequest.objects.filter(
                checkout_request_id=checkout_id,
                status='PENDING',
            ).update(
                status='FAILED',
                result_code=int(event.code) if event.code.lstrip('-').isdigit() else None,
                result_desc=event.result_desc,
            )
            if rows == 0:
                logger.info(
                    "STKCallbackView: duplicate failure callback for %s — ignored", checkout_id
                )

        return Response({"ResultCode": 0, "ResultDesc": "Accepted"})


class C2BValidationView(APIView):
    """Daraja validation URL — called before confirming a C2B payment."""
    permission_classes = [SafaricomIPPermission]

    def post(self, request):
        return Response({"ResultCode": 0, "ResultDesc": "Accepted"})


class C2BCallbackView(APIView):
    """
    Daraja confirmation URL — called when money actually hits the Paybill.
    Auto-reconciles payment to the correct contribution using AccountReference.
    """
    permission_classes = [SafaricomIPPermission]

    def post(self, request):
        data = request.data

        mpesa_receipt = data.get("TransID") or data.get("MpesaReceiptNumber")
        phone         = data.get("MSISDN") or data.get("PhoneNumber", "")
        amount        = data.get("TransAmount") or data.get("Amount", 0)
        bill_ref      = data.get("BillRefNumber") or data.get("AccountReference", "")
        trans_time    = data.get("TransTime") or data.get("TransactionDate", "")
        # Payer's registered M-Pesa name — Daraja sends these on C2B confirmation.
        first_name    = (data.get("FirstName") or "").strip()
        middle_name   = (data.get("MiddleName") or "").strip()
        last_name     = (data.get("LastName") or "").strip()

        if not mpesa_receipt:
            return Response({"ResultCode": 0, "ResultDesc": "Accepted"})

        # Idempotency: mpesa_receipt is unique on MpesaC2BTransaction
        if MpesaC2BTransaction.objects.filter(mpesa_receipt=mpesa_receipt).exists():
            return Response({"ResultCode": 0, "ResultDesc": "Accepted"})

        try:
            tx_date = datetime.strptime(str(trans_time), "%Y%m%d%H%M%S")
            tx_date = timezone.make_aware(tx_date)
        except (ValueError, TypeError):
            tx_date = timezone.now()

        tx = MpesaC2BTransaction.objects.create(
            phone_number=phone,
            amount=amount,
            mpesa_receipt=mpesa_receipt,
            transaction_date=tx_date,
            bill_ref_number=bill_ref,
            first_name=first_name,
            middle_name=middle_name,
            last_name=last_name,
        )

        try:
            MpesaService.reconcile_c2b(tx)
        except Exception:
            logger.exception("C2B reconcile failed for receipt %s", mpesa_receipt)

        return Response({"ResultCode": 0, "ResultDesc": "Accepted"})


class B2CResultView(APIView):
    """
    Daraja async callback — called when a B2C payment succeeds or fails.

    Claims the linked FinancialTransaction's transition and emits one durable
    settlement event; the inline consumer propagates to the domain (ADR-0028).
    """
    permission_classes = [SafaricomIPPermission]

    def post(self, request):
        from .providers.registry import get_provider
        event           = get_provider().parse_callback(request.data, kind='payout')
        conversation_id = event.provider_ref

        if not conversation_id:
            return Response({"ResultCode": 0, "ResultDesc": "Accepted"})

        # Settle the provider-agnostic payment aggregate (ADR-0014) — best-effort,
        # and durably record the raw result callback for audit/replay first.
        try:
            from .services import PaymentService
            PaymentService.record_provider_event(
                provider=get_provider().name, event_type='payout_result',
                payload=request.data, provider_ref=conversation_id,
                signature_verified=allowlist_enforced(),
            )
            PaymentService.resolve(
                provider=get_provider().name, provider_ref=conversation_id,
                success=event.success, receipt=event.receipt or '',
                failure_code=event.code or '', failure_message=event.result_desc or '',
            )
        except Exception:
            logger.exception("PaymentIntent resolve (payout) failed for %s", conversation_id)

        # ── Resolve the FinancialTransaction ──────────────────────────────────
        from apps.ledger.models import FinancialTransaction
        from . import money_activity
        # The correlation id belongs to the PaymentIntent (ADR-0014/0030) and
        # nowhere else now that FT's rail columns are gone; the seam resolves it
        # to the movement.
        ft = money_activity.financial_transaction_for_ref(
            conversation_id, provider=get_provider().name)
        if ft is None:
            logger.warning(
                "B2CResultView: no FinancialTransaction for conversation_id=%s — ignoring.",
                conversation_id,
            )
            return Response({"ResultCode": 0, "ResultDesc": "Accepted"})

        from apps.core.events import emit_event

        if event.success:
            receipt = event.receipt or ""

            # Discovery: claim the FT transition and, atomically, emit ONE durable
            # settlement event (ADR-0028). Winning the PROCESSING→SUCCESS race is
            # the "I discovered it" signal; the inline settlement consumer then
            # propagates (advance domain + notify) exactly once. Emitting inside
            # the same transaction as the transition guarantees a won transition
            # always carries its event — closing the SUCCESS-but-unpropagated gap.
            try:
                with transaction.atomic():
                    # The receipt is recorded on the PaymentIntent by the
                    # resolve() above — the ledger holds no rail fields (ADR-0030).
                    ft.transition_to(FinancialTransaction.State.SUCCESS)
                    # Capture the recipient's registered M-Pesa name if disclosed.
                    if event.counterparty_name and not ft.counterparty_name:
                        ft.counterparty_name = event.counterparty_name
                        ft.save(update_fields=["counterparty_name"])
                    emit_event(
                        'payment.settled',
                        aggregate_key=f'ft:{ft.id}',
                        dedup_key=f'payment.settled:ft={ft.id}',
                        body={'ft_id': ft.id, 'receipt': receipt},
                    )
            except TransitionError:
                # Another witness already finalised this payout (idempotent).
                logger.warning(
                    "B2CResultView: FT %s already transitioned — conversation_id=%s",
                    ft.id, conversation_id,
                )
                return Response({"ResultCode": 0, "ResultDesc": "Accepted"})

        else:
            err = f"B2C ResultCode {event.code}: {event.result_desc}"
            logger.error(
                "B2CResultView: B2C failed for FT %s — %s", ft.id, err
            )
            # Discovery: claim FAILED and emit one durable failure event; the
            # consumer restores the reserved funds (ledger reversal) and resets the
            # domain object. Atomic with the transition (as above).
            try:
                with transaction.atomic():
                    ft.transition_to(FinancialTransaction.State.FAILED, failure_reason=err)
                    emit_event(
                        'payment.failed',
                        aggregate_key=f'ft:{ft.id}',
                        dedup_key=f'payment.failed:ft={ft.id}',
                        body={'ft_id': ft.id, 'reason': err},
                    )
            except TransitionError:
                pass

        return Response({"ResultCode": 0, "ResultDesc": "Accepted"})


class B2CTimeoutView(APIView):
    """Daraja timeout URL — called when a B2C request times out."""
    permission_classes = [SafaricomIPPermission]

    def post(self, request):
        logger.warning("B2C timeout received: %s", request.data)
        return Response({"ResultCode": 0, "ResultDesc": "Accepted"})


class PendingSTKStatusView(APIView):
    """Poll the status of an STK Push request."""

    def get(self, request, checkout_request_id):
        stk = get_object_or_404(
            MpesaSTKRequest,
            checkout_request_id=checkout_request_id,
            user=request.user,
        )
        return Response({"status": stk.status, "mpesa_receipt": stk.mpesa_receipt})
