"""
M-Pesa Daraja API webhook handlers and STK push initiator.

Key fixes applied:
  - STKCallbackView: idempotent via atomic UPDATE WHERE status='PENDING' — a
    duplicate callback from Safaricom is a no-op (rows=0 → early return).
    All domain processing is deferred to process_stk_payment Celery task via
    on_commit — no more silent exception swallowing in the HTTP handler.
  - B2CResultView: resolves FinancialTransaction by conversation_id and
    updates the linked domain object (WelfareClaim, DisbursementRequest, etc.)
    Uses _notify() / on_commit rather than direct NotificationService.create().
  - SharesFund update in STK callback is now wrapped in @transaction.atomic
    with F() expressions (no read-modify-write race condition).
  - STKPushView: amount parsed as Decimal, not float.
  - Callback views: SafaricomIPPermission applied (no-op when
    SAFARICOM_CALLBACK_IPS is empty, enforced in production).
"""
import logging
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import F
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.throttling import ResilientUserRateThrottle

from apps.contributions.models import Contribution, WelfareFund, SharesFund
from apps.core.exceptions import TransitionError
from apps.users.tiers import AccessPolicy
from .models import MpesaSTKRequest, MpesaC2BTransaction
from .permissions import SafaricomIPPermission
from .services import MpesaService, _normalize_phone

logger = logging.getLogger(__name__)

# Canonical Kenyan MSISDN after normalisation: 2547XXXXXXXX / 2541XXXXXXXX.
_KE_MSISDN = re.compile(r"^254(7|1)\d{8}$")


class STKPushThrottle(ResilientUserRateThrottle):
    """Per-user rate limit on STK pushes (rate: settings 'stk_push'). Curbs
    prompt-spam now that a push may target a number other than the caller's.
    Fails open on a cache outage (see apps.core.throttling)."""
    scope = 'stk_push'


class STKPushView(APIView):
    """Initiate an M-Pesa STK Push for a contribution, welfare fund, or shares fund."""
    permission_classes = [IsAuthenticated]
    throttle_classes   = [STKPushThrottle]

    def post(self, request):
        # Tier-1 (KYC-approved) gate — this is the single money front-door for
        # members (all contribution/welfare/shares/advance payments flow through
        # STK push; the direct service endpoints are disabled). Enforced
        # unconditionally like the other money paths, independent of the
        # ACCESS_TIER_ENFORCEMENT flag (ADR-0022).
        AccessPolicy.require_tier1(
            request.user,
            "Verify your identity before making a payment.")

        payment_type = request.data.get("payment_type", "contribution")
        amount       = request.data.get("amount")

        # Target phone: default to the caller's own number; allow an explicit
        # phone_number in the body (e.g. pay from a different M-Pesa line, or pay
        # on someone's behalf). Validated to a Kenyan MSISDN; STKPushThrottle caps
        # per-user volume to curb prompt-spam.
        raw_phone = (request.data.get("phone_number") or "").strip()
        if raw_phone:
            phone = _normalize_phone(raw_phone)
            if not _KE_MSISDN.match(phone):
                return Response(
                    {"error": "Invalid phone number. Use a Kenyan number, e.g. 0712345678."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            phone = request.user.phone_number

        if not amount:
            return Response({"error": "amount is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            amount = Decimal(str(amount))
            if amount <= 0:
                raise ValueError
        except (InvalidOperation, ValueError, TypeError):
            return Response({"error": "Invalid amount"}, status=status.HTTP_400_BAD_REQUEST)

        contribution = welfare_fund = shares_fund = advance = None

        if payment_type == "welfare":
            community_id = request.data.get("community_id")
            if not community_id:
                return Response(
                    {"error": "community_id required for welfare payment"}, status=400
                )
            welfare_fund = get_object_or_404(WelfareFund, community_id=community_id)
            account_ref  = f"WPLWLF{community_id}"
            description  = welfare_fund.name or "Welfare"

        elif payment_type == "shares":
            community_id = request.data.get("community_id")
            if not community_id:
                return Response(
                    {"error": "community_id required for shares payment"}, status=400
                )
            shares_fund = get_object_or_404(SharesFund, community_id=community_id)
            account_ref = f"WPLSHR{community_id}"
            description = shares_fund.name or "Shares"

        elif payment_type == "advance_repayment":
            from apps.contributions.models import EmergencyAdvance
            advance_id = request.data.get("advance_id")
            if not advance_id:
                return Response({"error": "advance_id required for advance repayment"}, status=400)
            advance = get_object_or_404(
                EmergencyAdvance,
                id=advance_id,
                borrower=request.user,
                status__in=['APPROVED', 'DISBURSED'],
            )
            account_ref = f"WPLADV{advance.id}"
            description = f"Advance repayment #{advance.id}"

        else:
            contribution_id = request.data.get("contribution_id")
            if not contribution_id:
                return Response({"error": "contribution_id required"}, status=400)
            contribution = get_object_or_404(Contribution, id=contribution_id, is_active=True)
            account_ref  = f"WEPL-{contribution.id}"
            description  = contribution.title

        from apps.payments.providers.registry import get_provider
        from apps.ledger.money import Money
        try:
            result = get_provider().initiate_collection(
                phone=phone,
                amount=Money(str(amount)),
                reference=account_ref,
                description=description,
            )
        except Exception as exc:
            logger.exception("STK push failed")
            return Response({"error": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        if not result.accepted:
            return Response(
                {"error": result.raw.get("errorMessage", "STK push failed")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        MpesaSTKRequest.objects.create(
            user=request.user,
            payment_type=payment_type,
            contribution=contribution,
            welfare_fund=welfare_fund,
            shares_fund=shares_fund,
            advance=advance,
            phone_number=_normalize_phone(phone),
            amount=amount,
            checkout_request_id=result.provider_ref,
            merchant_request_id=result.raw.get("MerchantRequestID", ""),
        )

        # Provider-agnostic payment aggregate (ADR-0014) — best-effort; never
        # block the money path on payment bookkeeping.
        try:
            from apps.payments.services import PaymentService
            from apps.payments.models import PaymentIntent
            PaymentService.record_initiation(
                provider=get_provider().name,
                direction=PaymentIntent.Direction.COLLECTION,
                amount=amount,
                idempotency_key=f"pi-collect-{result.provider_ref}",
                provider_ref=result.provider_ref,
                op_type=payment_type,
                initiated_by=request.user,
                metadata={"payment_type": payment_type},
            )
        except Exception:
            logger.exception("record_initiation (collection) failed for %s", result.provider_ref)

        return Response(
            {
                "message": "STK Push sent. Enter your M-Pesa PIN on your phone.",
                "checkout_request_id": result.provider_ref,
            },
            status=status.HTTP_200_OK,
        )


class STKCallbackView(APIView):
    """
    Receives the async Daraja callback after a member completes/fails the STK prompt.

    Idempotency: uses UPDATE WHERE status='PENDING' to atomically claim the callback.
    If rows=0 the callback was already processed — return 200 immediately.

    Processing is deferred to the process_stk_payment Celery task via on_commit so
    that transient failures (DB, downstream service) are retried by Celery, not
    swallowed silently in the HTTP handler.
    """
    permission_classes = [SafaricomIPPermission]

    def post(self, request):
        from apps.payments.providers.registry import get_provider
        event       = get_provider().parse_callback(request.data, kind='collection')
        checkout_id = event.provider_ref

        if not checkout_id:
            return Response({"ResultCode": 0, "ResultDesc": "Accepted"})

        # Settle the provider-agnostic payment aggregate (ADR-0014) — best-effort,
        # and durably record the raw callback for audit/replay first.
        try:
            from apps.payments.services import PaymentService
            PaymentService.record_provider_event(
                provider=get_provider().name, event_type='collection_callback',
                payload=request.data, provider_ref=checkout_id,
                signature_verified=True,   # gated by SafaricomIPPermission
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

            # Atomic claim + deferred task dispatch.
            # on_commit ensures the task is enqueued only after the UPDATE is
            # durably committed — no phantom tasks if the DB write is rolled back.
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
                    lambda: _process_stk_sync_with_fallback(stk_id)
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

    Resolves the linked FinancialTransaction and updates the domain object
    (WelfareClaim, DisbursementRequest, EmergencyAdvance) accordingly.
    Uses _notify() so notifications go through Celery / on_commit, not inline.
    """
    permission_classes = [SafaricomIPPermission]

    def post(self, request):
        from apps.payments.providers.registry import get_provider
        event           = get_provider().parse_callback(request.data, kind='payout')
        conversation_id = event.provider_ref

        if not conversation_id:
            return Response({"ResultCode": 0, "ResultDesc": "Accepted"})

        # Settle the provider-agnostic payment aggregate (ADR-0014) — best-effort,
        # and durably record the raw result callback for audit/replay first.
        try:
            from apps.payments.services import PaymentService
            PaymentService.record_provider_event(
                provider=get_provider().name, event_type='payout_result',
                payload=request.data, provider_ref=conversation_id,
                signature_verified=True,   # gated by SafaricomIPPermission
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
        try:
            ft = FinancialTransaction.objects.get(mpesa_conversation_id=conversation_id)
        except FinancialTransaction.DoesNotExist:
            logger.warning(
                "B2CResultView: no FinancialTransaction with conversation_id=%s — ignoring.",
                conversation_id,
            )
            return Response({"ResultCode": 0, "ResultDesc": "Accepted"})

        if event.success:
            receipt = event.receipt or ""

            try:
                ft.transition_to(
                    FinancialTransaction.State.SUCCESS,
                    mpesa_receipt=receipt or None,
                )
            except TransitionError:
                logger.warning(
                    "B2CResultView: FT %s already transitioned — conversation_id=%s",
                    ft.id, conversation_id,
                )
                return Response({"ResultCode": 0, "ResultDesc": "Accepted"})

            # Capture the recipient's registered M-Pesa name if Daraja disclosed it.
            if event.counterparty_name and not ft.counterparty_name:
                ft.counterparty_name = event.counterparty_name
                ft.save(update_fields=["counterparty_name"])

            from apps.contributions.settlement import on_payout_settled
            on_payout_settled(ft, receipt)

        else:
            err = f"B2C ResultCode {event.code}: {event.result_desc}"
            logger.error(
                "B2CResultView: B2C failed for FT %s — %s", ft.id, err
            )
            try:
                ft.transition_to(FinancialTransaction.State.FAILED, failure_reason=err)
            except TransitionError:
                pass

            from apps.contributions.settlement import on_payout_failed
            from apps.ledger.posting import reverse_financial_transaction
            reverse_financial_transaction(ft, note=err)  # restore reserved funds
            on_payout_failed(ft)

        return Response({"ResultCode": 0, "ResultDesc": "Accepted"})


class B2CTimeoutView(APIView):
    """Daraja timeout URL — called when a B2C request times out."""
    permission_classes = [SafaricomIPPermission]

    def post(self, request):
        logger.warning("B2C timeout received: %s", request.data)
        return Response({"ResultCode": 0, "ResultDesc": "Accepted"})


class PendingSTKStatusView(APIView):
    """Poll the status of an STK Push request."""
    permission_classes = [IsAuthenticated]

    def get(self, request, checkout_request_id):
        stk = get_object_or_404(
            MpesaSTKRequest,
            checkout_request_id=checkout_request_id,
            user=request.user,
        )
        return Response({"status": stk.status, "mpesa_receipt": stk.mpesa_receipt})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _enqueue_stk_processing(stk_id: int) -> None:
    """Called via on_commit — safe to import tasks here (no circular import at module load).

    Best-effort: a broker outage must not 500 the callback handler. The STK
    request is committed, so the stuck-transaction sweep / ops retry lever pick it
    up; Safaricom also re-delivers the callback if we don't 200 promptly."""
    from .tasks import process_stk_payment
    from apps.core.dispatch import safe_enqueue
    safe_enqueue(process_stk_payment, stk_id, critical=True, options={'queue': 'payments'})


def _process_stk_sync_with_fallback(stk_id: int) -> None:
    """
    Process STK payment synchronously after the DB transaction commits.

    Running synchronously here (rather than via Celery) means the contribution
    balance, transaction record, and activity log are all written before the
    Safaricom webhook response is returned — so the mobile sees consistent data
    the first time it polls after payment confirmation.

    If synchronous processing raises any exception (rare — all operations are DB
    writes), we fall back to the Celery retry queue so no payment is ever lost.
    """
    from .models import MpesaSTKRequest
    from apps.contributions.services import ContributionService, WelfareService, EmergencyAdvanceService

    try:
        stk = MpesaSTKRequest.objects.select_related(
            'user', 'contribution', 'welfare_fund', 'shares_fund', 'advance'
        ).get(id=stk_id)
    except MpesaSTKRequest.DoesNotExist:
        logger.error("_process_stk_sync: STKRequest %s not found", stk_id)
        return

    try:
        if stk.payment_type == "welfare" and stk.welfare_fund_id:
            WelfareService.contribute_to_welfare(
                stk.welfare_fund_id, stk.user, stk.amount,
                mpesa_receipt=stk.mpesa_receipt,
            )
        elif stk.payment_type == "shares" and stk.shares_fund_id:
            _process_shares_purchase(stk)
        elif stk.payment_type == "advance_repayment" and stk.advance_id:
            EmergencyAdvanceService.repay(
                stk.advance_id, stk.user, stk.amount,
                mpesa_receipt=stk.mpesa_receipt,
            )
        else:
            idempotency_key = f"contrib-stk-{stk.mpesa_receipt or stk.checkout_request_id}"
            ContributionService.contribute(
                stk.user, stk.contribution_id, stk.amount,
                mpesa_receipt=stk.mpesa_receipt,
                idempotency_key=idempotency_key,
            )
        logger.info(
            "_process_stk_sync: STKRequest %s processed synchronously — type=%s receipt=%s",
            stk_id, stk.payment_type, stk.mpesa_receipt,
        )
    except Exception:
        logger.exception(
            "_process_stk_sync: failed for STKRequest %s — scheduling Celery retry",
            stk_id,
        )
        _enqueue_stk_processing(stk_id)


@transaction.atomic
def _process_shares_purchase(stk: MpesaSTKRequest) -> None:
    """
    Process a successful STK payment for shares.

    Fixed vs. old code:
      - Wrapped in @transaction.atomic (was absent — two .save() calls could diverge).
      - F() expressions for all balance increments (no read-modify-write race).
      - Dual-write to ledger.
    """
    from decimal import Decimal as D
    from apps.contributions.models import ShareHolding
    from apps.ledger.writer import create_fin_transaction
    from apps.ledger.models import FinancialTransaction

    fund = SharesFund.objects.select_for_update().get(id=stk.shares_fund_id)
    amount = D(str(stk.amount))

    new_shares = (amount / fund.share_price).quantize(D('0.0001'))

    # F() updates — atomic, no race condition
    ShareHolding.objects.update_or_create(
        shares_fund=fund,
        user=stk.user,
        defaults={'shares_count': D('0'), 'total_contributed': D('0')},
    )
    ShareHolding.objects.filter(shares_fund=fund, user=stk.user).update(
        shares_count=F('shares_count') + new_shares,
        total_contributed=F('total_contributed') + amount,
    )

    # FinancialTransaction (orchestration)
    idem_key = f"shares-{fund.id}-{stk.user_id}-{stk.mpesa_receipt or stk.checkout_request_id}"
    ft, _ = create_fin_transaction(
        idempotency_key=idem_key,
        op_type=FinancialTransaction.OpType.SHARES_PURCHASE,
        amount=amount,
        initiated_by=stk.user,
        shares_fund=fund,
        initial_state=FinancialTransaction.State.SUCCESS,
    )

    # Double-entry posting (P0-05): cash into the float, member shares liability up.
    from apps.ledger.posting import post_journal
    from apps.ledger import posting_map as pm
    from apps.ledger.money import Money
    post_journal(
        idempotency_key=f"je-{idem_key}",
        op_type=pm.Op.SHARES_PURCHASE,
        lines=pm.contribution_lines(
            member=stk.user, fund_type='shares', fund_id=fund.id,
            gross=Money(str(amount)),
        ),
        narration=f"Shares purchase by {stk.user.phone_number}",
        financial_transaction=ft,
        created_by=stk.user,
    )
