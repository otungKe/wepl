from ._common import *  # shared imports + helpers (ADR-0013 view split)


class StandingOrderListCreateView(APIView):
    permission_classes = [IsActiveSession]

    def get(self, request, contribution_id):
        contribution = get_object_or_404(Contribution, id=contribution_id)
        denied = _member_only(contribution, request.user)
        if denied:
            return denied
        orders = StandingOrderService.get_standing_orders(contribution_id)
        return Response(StandingOrderSerializer(orders, many=True).data)

    def post(self, request, contribution_id):
        required = ['amount', 'frequency', 'payee_type']
        for field in required:
            if not request.data.get(field):
                return Response({"error": f"{field} is required."}, status=status.HTTP_400_BAD_REQUEST)
        if request.data.get('payee_type') == 'fixed' and not request.data.get('fixed_payee_phone'):
            return Response({"error": "fixed_payee_phone is required for fixed payee type."}, status=status.HTTP_400_BAD_REQUEST)
        order = StandingOrderService.create_standing_order(request.user, contribution_id, request.data)
        return Response(StandingOrderSerializer(order).data, status=status.HTTP_201_CREATED)


class StandingOrderExecuteView(APIView):
    permission_classes = [IsActiveSession]

    def post(self, request, order_id):
        order = StandingOrderService.execute_standing_order(order_id, request.user)
        return Response(StandingOrderSerializer(order).data)


class StandingOrderCancelView(APIView):
    permission_classes = [IsActiveSession]

    def post(self, request, order_id):
        order = StandingOrderService.cancel_standing_order(order_id, request.user)
        return Response(StandingOrderSerializer(order).data)


class StandingOrderUpdateView(APIView):
    """PATCH standing-orders/<order_id>/update/ — amend amount, frequency, or fixed_payee_phone."""
    permission_classes = [IsActiveSession]

    def patch(self, request, order_id):
        allowed = {'amount', 'frequency', 'fixed_payee_phone'}
        data = {k: v for k, v in request.data.items() if k in allowed}
        if not data:
            return Response(
                {"error": "Provide at least one of: amount, frequency, fixed_payee_phone."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        order = StandingOrderService.update_standing_order(order_id, request.user, data)
        return Response(StandingOrderSerializer(order).data)


# ---------------------------------------------------------------------------
# Contribution Amendments
# ---------------------------------------------------------------------------
