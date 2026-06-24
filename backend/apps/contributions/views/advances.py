from ._common import *  # shared imports + helpers (ADR-0013 view split)


class AdvanceListCreateView(APIView):
    permission_classes = [IsActiveSession]

    def get(self, request, contribution_id):
        contribution = get_object_or_404(Contribution, id=contribution_id)
        denied = _member_only(contribution, request.user)
        if denied:
            return denied
        advances = EmergencyAdvance.objects.filter(
            contribution_id=contribution_id
        ).select_related('borrower').order_by('-created_at')
        paginator = FinancialCursorPagination()
        page = paginator.paginate_queryset(advances, request)
        return paginator.get_paginated_response(
            EmergencyAdvanceSerializer(page, many=True).data
        )

    def post(self, request, contribution_id):
        amount        = request.data.get('amount')
        interest_rate = request.data.get('interest_rate', '10.00')
        repayment_due = request.data.get('repayment_due')
        if not amount:
            return Response({"error": "amount required"}, status=status.HTTP_400_BAD_REQUEST)
        advance = EmergencyAdvanceService.request_advance(
            contribution_id, request.user, amount, interest_rate, repayment_due
        )
        logger.info(
            "AdvanceListCreateView: user %s requested advance %s for KES %s "
            "on contribution %s",
            request.user.id, advance.id, amount, contribution_id,
        )
        return Response(EmergencyAdvanceSerializer(advance).data, status=status.HTTP_201_CREATED)


class AdvanceActionView(APIView):
    permission_classes = [IsActiveSession]

    def post(self, request, advance_id):
        action = request.data.get('action', '').lower()
        if action == 'approve':
            advance = EmergencyAdvanceService.approve_advance(advance_id, request.user)
            logger.info(
                "AdvanceActionView: user %s approved advance %s", request.user.id, advance_id,
            )
        elif action == 'reject':
            advance = EmergencyAdvanceService.reject_advance(advance_id, request.user)
            logger.info(
                "AdvanceActionView: user %s rejected advance %s", request.user.id, advance_id,
            )
        elif action == 'repay':
            # DISABLED — advance repayments are M-Pesa only.
            return Response(
                {
                    "error": (
                        "Direct repayments are disabled. "
                        "Use M-Pesa STK Push: POST /api/mpesa/stk-push/ "
                        "with payment_type='advance_repayment' and advance_id."
                    ),
                    "mpesa_endpoint": "/api/mpesa/stk-push/",
                },
                status=status.HTTP_405_METHOD_NOT_ALLOWED,
            )
        else:
            return Response({"error": "action must be approve, reject, or repay"}, status=status.HTTP_400_BAD_REQUEST)
        return Response(EmergencyAdvanceSerializer(advance).data)


class MyAdvancesView(APIView):
    permission_classes = [IsActiveSession]

    def get(self, request):
        advances = EmergencyAdvance.objects.filter(
            borrower=request.user
        ).select_related('borrower').order_by('-created_at')
        paginator = FinancialCursorPagination()
        page = paginator.paginate_queryset(advances, request)
        return paginator.get_paginated_response(
            EmergencyAdvanceSerializer(page, many=True).data
        )


# ---------------------------------------------------------------------------
# Standing Orders
# ---------------------------------------------------------------------------
