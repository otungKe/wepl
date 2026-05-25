"""
Payment views.

Manual payment creation (PaymentCreateView) has been removed.
All contributions are now exclusively M-Pesa-driven via:
  POST /api/mpesa/stk-push/?payment_type=contribution

ContributionPaymentsView is retained as READ-ONLY for historical records.
"""
import logging

from django.shortcuts import get_object_or_404

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from apps.core.pagination import FinancialCursorPagination
from apps.contributions.models import Contribution, ContributionParticipant

from .models import Payment
from .serializers import PaymentSerializer

logger = logging.getLogger(__name__)


class ContributionPaymentsView(APIView):
    """
    Read-only list of legacy Payment records for a contribution.

    These records were created before M-Pesa-only mode was enforced.
    No new records are created through this path.

    Requires the requesting user to be an active participant in the contribution
    (prevents IDOR enumeration of financial data across contributions).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, contribution_id):
        contribution = get_object_or_404(Contribution, id=contribution_id)

        # IDOR guard: only active participants may see this contribution's payment history
        is_participant = ContributionParticipant.objects.filter(
            contribution=contribution,
            user=request.user,
            is_active=True,
        ).exists()
        is_creator = contribution.created_by_id == request.user.id

        if not is_participant and not is_creator:
            return Response(
                {"error": "You are not a participant in this contribution."},
                status=status.HTTP_403_FORBIDDEN,
            )

        payments = Payment.objects.filter(
            contribution=contribution
        ).select_related('user', 'recorded_by').order_by('-created_at')

        paginator = FinancialCursorPagination()
        page = paginator.paginate_queryset(payments, request)
        return paginator.get_paginated_response(
            PaymentSerializer(page, many=True).data
        )
