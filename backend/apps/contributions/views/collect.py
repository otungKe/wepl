"""The pay-in endpoint: STK push against a contribution, fund, or advance.

This is a *domain* endpoint, not a rail one. Deciding what is being paid for —
which contribution, welfare fund, shares fund or advance, and whether this payer
has cleared the Tier-1 gate — is this app's business. Only once that is settled
does it hand off to ``apps.payments``, which talks to the provider and keeps the
rail and ``PaymentIntent`` records.

It lived in ``apps/mpesa/views.py``, which is why the rail app used to import the
whole contribution model layer; moving it here is what let ``apps.mpesa`` become a
leaf (ADR-0033). The URL it answers, ``/api/mpesa/stk/push/``, is unchanged — see
``config/urls_mpesa.py``.
"""
import logging
from decimal import Decimal, InvalidOperation

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.throttling import ResilientUserRateThrottle
from apps.payments.collection import (
    CollectionUnavailable, normalized_msisdn, start_collection,
)
from apps.users.tiers import AccessPolicy

from ..models import Contribution, EmergencyAdvance, SharesFund, WelfareFund

logger = logging.getLogger(__name__)


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
            phone = normalized_msisdn(raw_phone)
            if phone is None:
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
            if welfare_fund.closed_at:
                return Response(
                    {"error": "This welfare fund has been wound up."}, status=400
                )
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

        try:
            started = start_collection(
                user=request.user,
                phone=phone,
                amount=amount,
                reference=account_ref,
                description=description,
                payment_type=payment_type,
                contribution_id=contribution.id if contribution else None,
                welfare_fund_id=welfare_fund.id if welfare_fund else None,
                shares_fund_id=shares_fund.id if shares_fund else None,
                advance_id=advance.id if advance else None,
            )
        except CollectionUnavailable:
            # The provider's own exception text can carry internals — a Daraja
            # URL, a stack frame, a credential-shaped token — so it does not
            # reach the caller (CodeQL: information exposure through an
            # exception). start_collection has already logged the detail. This
            # tightens what the endpoint used to return in apps/mpesa/views.py.
            return Response(
                {"error": "Could not reach M-Pesa just now. Please try again."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if not started.accepted:
            return Response({"error": started.error}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "message": "STK Push sent. Enter your M-Pesa PIN on your phone.",
                "checkout_request_id": started.provider_ref,
            },
            status=status.HTTP_200_OK,
        )
