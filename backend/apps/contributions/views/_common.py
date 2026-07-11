import logging
from decimal import Decimal, InvalidOperation

from django.shortcuts import get_object_or_404

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from apps.core.pagination import FinancialCursorPagination
from apps.core.policy import can, require
from apps.users.auth import IsActiveSession

logger = logging.getLogger(__name__)

MAX_SINGLE_CONTRIBUTION = Decimal('1000000')

from ..models import (
    Contribution, ContributionParticipant, ContributionTransaction,
    DisbursementRequest,
    WelfareFund, WelfareClaim, EmergencyAdvance, SharesFund, ShareHolding,
    StandingOrder, ContributionAmendment, ContributionJoinRequest,
)

from ..serializers import (
    ContributionSerializer, ContributionParticipantSerializer,
    ContributionPaymentSerializer, ContributionTransactionSerializer,
    ROSCASlotSerializer, DisbursementRequestSerializer,
    SharesFundSerializer,
    WelfareFundSerializer, WelfareContributionSerializer, WelfareClaimSerializer,
    EmergencyAdvanceSerializer,
    StandingOrderSerializer,
    ContributionAmendmentSerializer,
    ContributionJoinRequestSerializer,
)
from ..services import (
    ContributionService, ROSCAService, DisbursementService,
    WelfareService, EmergencyAdvanceService,
    StandingOrderService, AmendmentService, ContributionJoinRequestService,
)


def _is_contribution_member(contribution, user) -> bool:
    """Return True if user is the creator OR an active participant (ADR-0009)."""
    return can(user, "contribution.view", contribution)


def _member_only(contribution, user):
    """Return a 403 Response if user is not a member; None otherwise."""
    if not _is_contribution_member(contribution, user):
        return Response(
            {"error": "You are not a participant in this contribution."},
            status=status.HTTP_403_FORBIDDEN,
        )
    return None


# ---------------------------------------------------------------------------
# Core contribution CRUD
# ---------------------------------------------------------------------------

# Export every top-level name so each view sub-module gets the shared
# imports/helpers via `from ._common import *` (ADR-0013).
__all__ = [n for n in dir() if not n.startswith('__')]
