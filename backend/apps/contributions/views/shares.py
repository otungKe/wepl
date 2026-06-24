from ._common import *  # shared imports + helpers (ADR-0013 view split)


class CommunitySharesFundView(APIView):
    permission_classes = [IsActiveSession]

    def get(self, request, community_id):
        fund = get_object_or_404(SharesFund, community_id=community_id)
        return Response(SharesFundSerializer(fund).data)


class CommunitySharesContributeView(APIView):
    """
    DISABLED: All shares contributions must go through M-Pesa STK push.
    Use POST /api/mpesa/stk-push/ with payment_type='shares' instead.
    """
    permission_classes = [IsActiveSession]

    def post(self, request, community_id):
        return Response(
            {"error": "Direct shares contributions are disabled. Use M-Pesa STK push (payment_type='shares')."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )
