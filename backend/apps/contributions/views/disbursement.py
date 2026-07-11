from ._common import *  # shared imports + helpers (ADR-0013)


class DisbursementRequestListCreateView(APIView):
    permission_classes = [IsActiveSession]

    def get(self, request, contribution_id):
        contribution = get_object_or_404(Contribution, id=contribution_id)
        denied = _member_only(contribution, request.user)
        if denied:
            return denied
        reqs = DisbursementRequest.objects.filter(
            contribution_id=contribution_id
        ).select_related('requested_by').prefetch_related('votes__voter').order_by('-created_at')
        paginator = FinancialCursorPagination()
        page = paginator.paginate_queryset(reqs, request)
        return paginator.get_paginated_response(
            DisbursementRequestSerializer(page, many=True).data
        )

    def post(self, request, contribution_id):
        amount          = request.data.get('amount')
        reason          = request.data.get('reason', '')
        recipient_phone = request.data.get('recipient_phone', request.user.phone_number)
        if not amount or not reason:
            return Response({"error": "amount and reason are required"}, status=status.HTTP_400_BAD_REQUEST)
        req = DisbursementService.create_request(
            contribution_id, request.user, amount, reason, recipient_phone
        )
        logger.info(
            "DisbursementRequestListCreateView: user %s created disbursement request %s "
            "for KES %s on contribution %s",
            request.user.id, req.id, amount, contribution_id,
        )
        return Response(DisbursementRequestSerializer(req).data, status=status.HTTP_201_CREATED)


class DisbursementVoteView(APIView):
    permission_classes = [IsActiveSession]

    def post(self, request, request_id):
        vote_choice = request.data.get('vote', '').upper()
        if vote_choice not in ('APPROVE', 'REJECT'):
            return Response({"error": "vote must be APPROVE or REJECT"}, status=status.HTTP_400_BAD_REQUEST)
        req = DisbursementService.vote(request_id, request.user, vote_choice)
        logger.info(
            "DisbursementVoteView: user %s cast %s on disbursement request %s",
            request.user.id, vote_choice, request_id,
        )
        return Response(DisbursementRequestSerializer(req).data)


class DisbursementCancelView(APIView):
    """Allow the requester to withdraw a pending disbursement request."""
    permission_classes = [IsActiveSession]

    def post(self, request, request_id):
        req = DisbursementService.cancel_request(request_id, request.user)
        return Response(DisbursementRequestSerializer(req).data)


# ---------------------------------------------------------------------------
# Shares Fund (community-scoped)
# ---------------------------------------------------------------------------
