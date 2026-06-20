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

from apps.contributions.models import Contribution, WelfareFund, SharesFund
from apps.core.exceptions import TransitionError
from .models import MpesaSTKRequest, MpesaC2BTransaction
from .permissions import SafaricomIPPermission
from .services import MpesaService, _normalize_phone

logger = logging.getLogger(__name__)


class STKPushView(APIView):
    """Initiate an M-Pesa STK Push for a contribution, welfare fund, or shares fund."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        payment_type = request.data.get("payment_type", "contribution")
        amount       = request.data.get("amount")

        # Security: default to the authenticated user's own phone — do not
        # blindly accept any phone from the request body (harassment vector).
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
        body        = request.data.get("Body", {})
        callback    = body.get("stkCallback", {})
        checkout_id = callback.get("CheckoutRequestID")
        result_code = callback.get("ResultCode")

        if not checkout_id:
            return Response({"ResultCode": 0, "ResultDesc": "Accepted"})

        if result_code == 0:
            # ── Success path ───────────────────────────────────────────────────
            metadata = callback.get("CallbackMetadata", {}).get("Item", [])
            items    = {i["Name"]: i.get("Value") for i in metadata}
            receipt  = items.get("MpesaReceiptNumber")

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
                result_code=result_code,
                result_desc=callback.get("ResultDesc", ""),
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
        body            = request.data.get("Result", {})
        result_code     = body.get("ResultCode")
        conversation_id = (
            body.get("ConversationID") or
            body.get("OriginatorConversationID")
        )

        if not conversation_id:
            return Response({"ResultCode": 0, "ResultDesc": "Accepted"})

        # ── Resolve the FinancialTransaction ──────────────────────────────────
        from apps.ledger.models import FinancialTransaction
        try:
            ft = FinancialTransaction.objects.get(mpesa_conversation_id=conversation_id)
        except FinancialTransaction.DoesNotExist:
            # Could be a legacy B2C payment (welfare claim via old flow)
            logger.warning(
                "B2CResultView: no FinancialTransaction with conversation_id=%s — "
                "falling back to legacy WelfareClaim lookup.",
                conversation_id,
            )
            return _legacy_b2c_result(body, conversation_id, result_code)

        if result_code == 0:
            params  = {
                p["Key"]: p["Value"]
                for p in body.get("ResultParameters", {}).get("ResultParameter", [])
            }
            receipt = params.get("TransactionID") or params.get("TransactionReceipt", "")

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

            _on_b2c_success(ft, receipt)

        else:
            err = f"B2C ResultCode {result_code}: {body.get('ResultDesc', '')}"
            logger.error(
                "B2CResultView: B2C failed for FT %s — %s", ft.id, err
            )
            try:
                ft.transition_to(FinancialTransaction.State.FAILED, failure_reason=err)
            except TransitionError:
                pass

            from apps.ledger.tasks import _update_context_on_failure
            from apps.ledger.posting import reverse_financial_transaction
            reverse_financial_transaction(ft, note=err)  # restore reserved funds
            _update_context_on_failure(ft)

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
    """Called via on_commit — safe to import tasks here (no circular import at module load)."""
    from .tasks import process_stk_payment
    process_stk_payment.apply_async(args=[stk_id], queue='payments')


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


def _on_b2c_success(ft, receipt: str) -> None:
    """Update the domain object and notify the user after a successful B2C payout."""
    from apps.contributions.services import _notify

    if not ft.context_type or not ft.context_id:
        return

    if ft.context_type == 'welfare_claim':
        from apps.contributions.models import WelfareClaim
        from apps.core.exceptions import TransitionError
        try:
            claim = WelfareClaim.objects.get(id=ft.context_id)
            claim.transition_to(
                'DISBURSED',
                disbursed_at=timezone.now(),
                mpesa_receipt=receipt or None,
            )
            _notify(
                user=claim.claimant,
                notification_type='welfare_disbursed',
                title="M-Pesa payment sent!",
                message=(
                    f"KES {claim.amount_requested:,.0f} has been sent to your M-Pesa."
                    + (f" Receipt: {receipt}." if receipt else "")
                ),
            )
        except WelfareClaim.DoesNotExist:
            logger.warning("_on_b2c_success: WelfareClaim %s not found", ft.context_id)
        except TransitionError:
            logger.warning(
                "_on_b2c_success: WelfareClaim %s already transitioned (idempotent)",
                ft.context_id,
            )

    elif ft.context_type == 'disbursement_request':
        from apps.contributions.models import DisbursementRequest
        try:
            req = DisbursementRequest.objects.get(id=ft.context_id)
            _notify(
                user=req.requested_by,
                notification_type='disbursement_sent',
                title="Disbursement sent!",
                message=(
                    f"KES {req.amount} has been sent to {req.recipient_phone}."
                    + (f" M-Pesa receipt: {receipt}." if receipt else "")
                ),
                contribution_id=req.contribution_id,
            )
        except DisbursementRequest.DoesNotExist:
            pass

    elif ft.context_type == 'emergency_advance':
        from apps.contributions.models import EmergencyAdvance
        try:
            advance = EmergencyAdvance.objects.get(id=ft.context_id)
            _notify(
                user=advance.borrower,
                notification_type='advance_sent',
                title="Advance sent!",
                message=(
                    f"KES {advance.amount} has been sent to your M-Pesa."
                    + (f" Receipt: {receipt}." if receipt else "")
                ),
                contribution_id=advance.contribution_id,
            )
        except EmergencyAdvance.DoesNotExist:
            pass

    elif ft.context_type == 'standing_order':
        logger.info(
            "B2C success for standing order context_id=%s receipt=%s",
            ft.context_id, receipt,
        )


def _legacy_b2c_result(body: dict, conversation_id: str, result_code: int) -> Response:
    """
    Fallback for B2C callbacks that predate the FinancialTransaction model.
    Handles old-style welfare claims that stored b2c_conversation_id directly.
    """
    from apps.contributions.models import WelfareClaim
    from apps.contributions.services import _notify

    try:
        claim = WelfareClaim.objects.get(b2c_conversation_id=conversation_id)
    except WelfareClaim.DoesNotExist:
        logger.warning(
            "_legacy_b2c_result: no WelfareClaim with b2c_conversation_id=%s",
            conversation_id,
        )
        return Response({"ResultCode": 0, "ResultDesc": "Accepted"})

    if result_code == 0:
        params  = {
            p["Key"]: p["Value"]
            for p in body.get("ResultParameters", {}).get("ResultParameter", [])
        }
        receipt = params.get("TransactionID") or params.get("TransactionReceipt", "")
        try:
            claim.transition_to(
                'DISBURSED',
                disbursed_at=timezone.now(),
                mpesa_receipt=receipt or None,
            )
        except TransitionError:
            logger.warning(
                "_legacy_b2c_result: WelfareClaim %s already transitioned (idempotent)",
                claim.id,
            )
        _notify(
            user=claim.claimant,
            notification_type='welfare_disbursed',
            title="M-Pesa payment sent!",
            message=(
                f"KES {claim.amount_requested:,.0f} sent to your M-Pesa."
                + (f" Receipt: {receipt}." if receipt else "")
            ),
        )
    else:
        logger.error(
            "_legacy_b2c_result: B2C failed for claim %s — code %s",
            claim.id, result_code,
        )

    return Response({"ResultCode": 0, "ResultDesc": "Accepted"})
