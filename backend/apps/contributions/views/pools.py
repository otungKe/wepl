"""Collective-fund admin actions (ADR-0027).

A jointly-owned pool's money movements that aren't a single member's: spending on
a shared expense (apportioned across members), recording external/business
income (held collectively as retained surplus), and declaring a distribution of
that surplus into member positions. All are governed — the service enforces the
``contribution.admin`` gate — and posted through the ledger.
"""
from ._common import *  # shared imports + helpers (ADR-0013 view split)
from ..serializers import (
    PoolExpenseSerializer, ExternalIncomeSerializer, SurplusDistributionSerializer,
)


def _ref(ft):
    return Response({"reference": ft.reference, "id": ft.id}, status=status.HTTP_201_CREATED)


class PoolExpenseView(APIView):
    """POST /contributions/<id>/pool-expense/ — spend pool funds on a shared
    expense, apportioned across the funded members (admins only)."""
    permission_classes = [IsActiveSession]

    def post(self, request, contribution_id):
        s = PoolExpenseSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        ft = ContributionService.record_pool_expense(
            request.user, contribution_id, s.validated_data['amount'],
            apportion=s.validated_data['apportion'], reason=s.validated_data['reason'])
        return _ref(ft)


class ExternalIncomeView(APIView):
    """POST /contributions/<id>/external-income/ — record external/business
    proceeds into the pool's retained surplus (admins only)."""
    permission_classes = [IsActiveSession]

    def post(self, request, contribution_id):
        s = ExternalIncomeSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        ft = ContributionService.record_external_income(
            request.user, contribution_id, s.validated_data['amount'],
            source=s.validated_data['source'])
        return _ref(ft)


class SurplusDistributionView(APIView):
    """POST /contributions/<id>/distribute/ — declare a distribution of the pool's
    retained surplus into member positions (admins only)."""
    permission_classes = [IsActiveSession]

    def post(self, request, contribution_id):
        s = SurplusDistributionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        ft = ContributionService.declare_distribution(
            request.user, contribution_id, s.validated_data['amount'],
            apportion=s.validated_data['apportion'], reason=s.validated_data['reason'])
        return _ref(ft)
