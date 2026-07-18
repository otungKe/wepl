"""Collective-fund admin actions (ADR-0027).

Spending pool funds (an expense) and declaring a distribution move *members'*
money, so they are maker-checked: an admin *proposes*, a second admin *approves*,
then it posts through the ledger. External income (money in) is benign and stays
a direct admin action. Governance lives in PoolGovernanceService; the underlying
ledger execution in ContributionService.
"""
from ._common import *  # shared imports + helpers (ADR-0013 view split)
from ..serializers import (
    PoolExpenseSerializer, ExternalIncomeSerializer, SurplusDistributionSerializer,
    PoolActionRequestSerializer,
)
from ..models import PoolActionRequest
from ..services import PoolGovernanceService


class ExternalIncomeView(APIView):
    """POST /contributions/<id>/external-income/ — record external/business
    proceeds into the pool's retained surplus (admins only). Money in is benign,
    so this executes directly."""
    permission_classes = [IsActiveSession]

    def post(self, request, contribution_id):
        s = ExternalIncomeSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        ft = ContributionService.record_external_income(
            request.user, contribution_id, s.validated_data['amount'],
            source=s.validated_data['source'])
        return Response({"reference": ft.reference, "id": ft.id}, status=status.HTTP_201_CREATED)


class PoolExpenseRequestView(APIView):
    """POST /contributions/<id>/pool-expense/ — propose spending pool funds on a
    shared expense. Held for a second admin's approval."""
    permission_classes = [IsActiveSession]

    def post(self, request, contribution_id):
        s = PoolExpenseSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        req = PoolGovernanceService.request(
            request.user, contribution_id, action=PoolActionRequest.Action.EXPENSE,
            amount=s.validated_data['amount'], apportion=s.validated_data['apportion'],
            memo=s.validated_data['reason'])
        return Response(PoolActionRequestSerializer(req).data, status=status.HTTP_201_CREATED)


class SurplusDistributionRequestView(APIView):
    """POST /contributions/<id>/distribute/ — propose distributing the pool's
    retained surplus into member positions. Held for a second admin's approval."""
    permission_classes = [IsActiveSession]

    def post(self, request, contribution_id):
        s = SurplusDistributionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        req = PoolGovernanceService.request(
            request.user, contribution_id, action=PoolActionRequest.Action.DISTRIBUTION,
            amount=s.validated_data['amount'], apportion=s.validated_data['apportion'],
            memo=s.validated_data['reason'])
        return Response(PoolActionRequestSerializer(req).data, status=status.HTTP_201_CREATED)


class PoolActionListView(APIView):
    """GET /contributions/<id>/pool-actions/ — the collective-fund action log
    (pending + decided) for participants to see."""
    permission_classes = [IsActiveSession]

    def get(self, request, contribution_id):
        contribution = get_object_or_404(Contribution, id=contribution_id)
        require(request.user, "contribution.participate", contribution,
                "You are not a participant in this contribution.")
        qs = PoolActionRequest.objects.filter(contribution=contribution)
        return Response(PoolActionRequestSerializer(qs, many=True).data)


class PoolActionApproveView(APIView):
    """POST /contributions/pool-actions/<id>/approve/ — a second admin approves;
    on threshold the action executes through the ledger."""
    permission_classes = [IsActiveSession]

    def post(self, request, request_id):
        req = PoolGovernanceService.approve(request.user, request_id)
        return Response(PoolActionRequestSerializer(req).data)


class PoolActionRejectView(APIView):
    """POST /contributions/pool-actions/<id>/reject/ — a second admin rejects."""
    permission_classes = [IsActiveSession]

    def post(self, request, request_id):
        req = PoolGovernanceService.reject(
            request.user, request_id, note=request.data.get('reason', ''))
        return Response(PoolActionRequestSerializer(req).data)


class PoolActionCancelView(APIView):
    """POST /contributions/pool-actions/<id>/cancel/ — the maker withdraws it."""
    permission_classes = [IsActiveSession]

    def post(self, request, request_id):
        req = PoolGovernanceService.cancel(request.user, request_id)
        return Response(PoolActionRequestSerializer(req).data)
