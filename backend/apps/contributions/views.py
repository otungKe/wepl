from decimal import Decimal, InvalidOperation

from django.shortcuts import get_object_or_404

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from apps.core.pagination import FinancialCursorPagination

MAX_SINGLE_CONTRIBUTION = Decimal('1000000')

from .models import (
    Contribution, ContributionParticipant, ContributionTransaction,
    DisbursementRequest,
    WelfareFund, WelfareClaim, EmergencyAdvance, SharesFund, ShareHolding,
    StandingOrder, ContributionAmendment, ContributionJoinRequest,
)

from .serializers import (
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
from .services import (
    ContributionService, ROSCAService, DisbursementService,
    WelfareService, EmergencyAdvanceService,
    StandingOrderService, AmendmentService, ContributionJoinRequestService,
)


def _is_contribution_member(contribution, user) -> bool:
    """Return True if user is the creator OR an active participant."""
    if contribution.created_by_id == user.id:
        return True
    return ContributionParticipant.objects.filter(
        contribution=contribution, user=user, is_active=True
    ).exists()


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

class ContributionCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        member_phones   = request.data.get('member_phones', [])
        add_all_members = bool(request.data.get('add_all_members', False))
        share_price     = request.data.get('share_price')

        serializer = ContributionSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        community = serializer.validated_data.get('community')
        if community:
            from apps.communities.models import CommunityMembership
            is_admin = (
                community.created_by == request.user or
                CommunityMembership.objects.filter(
                    community=community, user=request.user,
                    role='admin', is_active=True
                ).exists()
            )
            if not is_admin:
                return Response(
                    {"error": "Only community admins can create contributions."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        contribution = ContributionService.create_contribution(
            request.user,
            serializer.validated_data,
            member_phones=member_phones,
            add_all_members=add_all_members,
        )
        return Response(
            ContributionSerializer(contribution, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )




class MyContributionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        active = request.query_params.get('active', 'true').lower() != 'false'
        contributions = ContributionService.get_user_contributions(request.user, active_only=active)
        paginator = FinancialCursorPagination()
        page = paginator.paginate_queryset(contributions, request)
        return paginator.get_paginated_response(
            ContributionSerializer(page, many=True, context={'request': request}).data
        )


class CommunityContributionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, community_id):
        from django.db.models import Count, Q, Prefetch
        from .models import ContributionBalance
        contributions = Contribution.objects.filter(
            community_id=community_id, is_active=True
        ).annotate(
            active_participant_count=Count(
                'participants', filter=Q(participants__is_active=True), distinct=True
            )
        ).prefetch_related(
            Prefetch(
                'balances',
                queryset=ContributionBalance.objects.filter(user=request.user),
                to_attr='_user_balance_list',
            )
        ).order_by('-created_at')
        paginator = FinancialCursorPagination()
        page = paginator.paginate_queryset(contributions, request)
        return paginator.get_paginated_response(
            ContributionSerializer(page, many=True, context={'request': request}).data
        )


class OpenContributionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.db.models import Count, Q, Prefetch
        from .models import ContributionBalance
        contributions = Contribution.objects.filter(
            visibility='open', is_active=True
        ).annotate(
            active_participant_count=Count(
                'participants', filter=Q(participants__is_active=True), distinct=True
            )
        ).prefetch_related(
            Prefetch(
                'balances',
                queryset=ContributionBalance.objects.filter(user=request.user),
                to_attr='_user_balance_list',
            )
        ).order_by('-created_at')
        paginator = FinancialCursorPagination()
        page = paginator.paginate_queryset(contributions, request)
        return paginator.get_paginated_response(
            ContributionSerializer(page, many=True, context={'request': request}).data
        )


class DiscoverCampaignsView(APIView):
    """
    GET /api/contributions/campaigns/
    Public fundraising campaigns (visibility='open', is_campaign=True).
    Query params:
      q      — title / description search
      limit  — default 30, max 100
      offset — pagination offset
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.db.models import Count, Q
        from django.utils import timezone

        q      = request.query_params.get('q', '').strip()
        limit  = min(int(request.query_params.get('limit',  30)), 100)
        offset = int(request.query_params.get('offset', 0))

        qs = (
            Contribution.objects
            .filter(visibility='open', is_active=True, is_campaign=True)
            .annotate(
                contributor_count=Count(
                    'participants',
                    filter=Q(participants__is_active=True),
                    distinct=True,
                )
            )
            .select_related('created_by', 'community')
            .order_by('-created_at')
        )

        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))

        total     = qs.count()
        campaigns = list(qs[offset: offset + limit])

        user = request.user
        joined_ids = set(
            ContributionParticipant.objects
            .filter(contribution__in=campaigns, user=user, is_active=True)
            .values_list('contribution_id', flat=True)
        )

        today = timezone.now().date()

        results = []
        for c in campaigns:
            target  = float(c.target_amount) if c.target_amount else None
            current = float(c.current_amount)
            progress_pct = (
                round(current / target * 100, 1) if target and target > 0 else None
            )
            if c.end_date:
                days_left = max(0, (c.end_date - today).days)
            else:
                days_left = None

            results.append({
                'id':                c.id,
                'title':             c.title,
                'description':       c.description,
                'target_amount':     target,
                'current_amount':    current,
                'progress_pct':      progress_pct,
                'days_left':         days_left,
                'contributor_count': c.contributor_count,
                'frequency':         c.frequency,
                'amount_type':       c.amount_type,
                'fixed_amount':      float(c.fixed_amount) if c.fixed_amount else None,
                'community':         c.community.name if c.community else None,
                'community_id':      c.community_id,
                'created_by':        (c.created_by.name or '').strip() or c.created_by.phone_number,
                'is_joined':         c.id in joined_ids,
                'invite_code':       c.invite_code,
                'created_at':        c.created_at,
            })

        return Response({
            'count':    total,
            'has_more': (offset + limit) < total,
            'results':  results,
        })


class ContributionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, contribution_id):
        from apps.communities.models import CommunityMembership
        c = get_object_or_404(Contribution, id=contribution_id)

        # Participants and the creator always get the full detail view.
        if _is_contribution_member(c, request.user):
            return Response(ContributionSerializer(c, context={'request': request}).data)

        # Non-participant: determine whether they can reach the request-to-join screen.
        if c.visibility == 'closed' and c.community:
            is_community_member = (
                c.community.created_by_id == request.user.id or
                CommunityMembership.objects.filter(
                    community=c.community, user=request.user, is_active=True
                ).exists()
            )
            if not is_community_member:
                return Response(
                    {"error": "not_community_member"},
                    status=status.HTTP_403_FORBIDDEN,
                )

        # Community member (or open contribution) but not yet a participant —
        # return minimal info so mobile can render the request-to-join screen.
        return Response(
            {"error": "not_participant", "id": c.id, "title": c.title, "status": c.status},
            status=status.HTTP_403_FORBIDDEN,
        )


class ContributionByInviteView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, invite_code):
        c = ContributionService.get_by_invite_code(invite_code)
        if not c:
            return Response({"error": "Invalid invite code"}, status=status.HTTP_404_NOT_FOUND)
        return Response(ContributionSerializer(c, context={'request': request}).data)


class JoinContributionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, contribution_id):
        participant = ContributionService.join_contribution(contribution_id, request.user)
        return Response(ContributionParticipantSerializer(participant).data)


class LeaveContributionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, contribution_id):
        ContributionService.leave_contribution(contribution_id, request.user)
        return Response({"message": "Left successfully"})


class ContributionCloseView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, contribution_id):
        c = ContributionService.close_contribution(contribution_id, request.user)
        return Response(ContributionSerializer(c, context={'request': request}).data)


class ContributionReopenView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, contribution_id):
        c = ContributionService.reopen_contribution(contribution_id, request.user)
        return Response(ContributionSerializer(c, context={'request': request}).data)


class ContributionArchiveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, contribution_id):
        c = ContributionService.archive_contribution(contribution_id, request.user)
        return Response(ContributionSerializer(c, context={'request': request}).data)


class ContributionUpdateView(APIView):
    """
    PATCH /contributions/<contribution_id>/update/
    Direct (immediate) edit — only cosmetic fields: title and description.
    Sensitive field changes (fixed_amount, target_amount, voting_threshold,
    end_date, period_months, visibility) must go through an amendment proposal.
    """
    permission_classes = [IsAuthenticated]
    DIRECT_FIELDS = {'title', 'description'}

    def patch(self, request, contribution_id):
        contribution = get_object_or_404(Contribution, id=contribution_id)

        is_creator = contribution.created_by == request.user
        is_admin = False
        if contribution.community:
            from apps.communities.models import CommunityMembership
            is_admin = CommunityMembership.objects.filter(
                community=contribution.community,
                user=request.user, role__in=['admin', 'treasurer'], is_active=True,
            ).exists()

        if not is_creator and not is_admin:
            return Response(
                {"error": "Only the contribution creator or a community admin can edit this contribution."},
                status=status.HTTP_403_FORBIDDEN,
            )

        payload = {k: v for k, v in request.data.items() if k in self.DIRECT_FIELDS}
        if not payload:
            return Response(
                {"error": "Only 'title' and 'description' can be edited directly. "
                          "Use POST /amendments/ for sensitive field changes."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = ContributionSerializer(contribution, data=payload, partial=True, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(ContributionSerializer(contribution, context={'request': request}).data)


class ContributionDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, contribution_id):
        ContributionService.delete_contribution(contribution_id, request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ContributionParticipantsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, contribution_id):
        ps = ContributionService.get_participants(contribution_id)
        return Response(ContributionParticipantSerializer(ps, many=True).data)


class ContributeView(APIView):
    """
    DISABLED — direct cash contributions are no longer accepted.

    All contributions must be made via M-Pesa STK Push:
      POST /api/mpesa/stk-push/
        { "payment_type": "contribution", "contribution_id": <id>, "amount": <amount> }

    This endpoint exists only to provide a clear migration error message.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        return Response(
            {
                "error": (
                    "Direct cash contributions are disabled. "
                    "Use M-Pesa STK Push: POST /api/mpesa/stk-push/ "
                    "with payment_type='contribution'."
                ),
                "mpesa_endpoint": "/api/mpesa/stk-push/",
            },
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )


class MyTransactionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        txs = ContributionTransaction.objects.filter(
            user=request.user
        ).select_related('user', 'contribution').order_by('-created_at')
        paginator = FinancialCursorPagination()
        page = paginator.paginate_queryset(txs, request)
        return paginator.get_paginated_response(
            ContributionTransactionSerializer(page, many=True).data
        )


class ContributionTransactionsView(APIView):
    """
    GET /contributions/<contribution_id>/transactions/
    Returns all transactions for a contribution — visible to any active participant.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, contribution_id):
        # Must be an active participant (or the creator)
        is_participant = ContributionParticipant.objects.filter(
            contribution_id=contribution_id,
            user=request.user,
            is_active=True,
        ).exists()
        if not is_participant:
            return Response(
                {"error": "You are not a participant in this contribution."},
                status=status.HTTP_403_FORBIDDEN,
            )
        txs = ContributionTransaction.objects.filter(
            contribution_id=contribution_id
        ).select_related('user', 'contribution').order_by('-created_at')
        paginator = FinancialCursorPagination()
        page = paginator.paginate_queryset(txs, request)
        return paginator.get_paginated_response(
            ContributionTransactionSerializer(page, many=True, context={'request': request}).data
        )


# ---------------------------------------------------------------------------
# ROSCA
# ---------------------------------------------------------------------------

class ROSCARotationView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, contribution_id):
        contribution = get_object_or_404(Contribution, id=contribution_id)
        denied = _member_only(contribution, request.user)
        if denied:
            return denied
        slots = ROSCAService.get_rotation_status(contribution_id)
        return Response(ROSCASlotSerializer(slots, many=True).data)

    def post(self, request, contribution_id):
        slots = ROSCAService.initialize_rotation(contribution_id, request.user)
        return Response(ROSCASlotSerializer(slots, many=True).data, status=status.HTTP_201_CREATED)


class ROSCAAdvanceSlotView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, contribution_id):
        slot = ROSCAService.mark_slot_paid(contribution_id, request.user)
        return Response(ROSCASlotSerializer(slot).data)


# ---------------------------------------------------------------------------
# Disbursement
# ---------------------------------------------------------------------------

class DisbursementRequestListCreateView(APIView):
    permission_classes = [IsAuthenticated]

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
        return Response(DisbursementRequestSerializer(req).data, status=status.HTTP_201_CREATED)


class DisbursementVoteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, request_id):
        vote_choice = request.data.get('vote', '').upper()
        if vote_choice not in ('APPROVE', 'REJECT'):
            return Response({"error": "vote must be APPROVE or REJECT"}, status=status.HTTP_400_BAD_REQUEST)
        req = DisbursementService.vote(request_id, request.user, vote_choice)
        return Response(DisbursementRequestSerializer(req).data)


class DisbursementCancelView(APIView):
    """Allow the requester to withdraw a pending disbursement request."""
    permission_classes = [IsAuthenticated]

    def post(self, request, request_id):
        req = DisbursementService.cancel_request(request_id, request.user)
        return Response(DisbursementRequestSerializer(req).data)


# ---------------------------------------------------------------------------
# Shares Fund (community-scoped)
# ---------------------------------------------------------------------------

class CommunitySharesFundView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, community_id):
        fund = get_object_or_404(SharesFund, community_id=community_id)
        return Response(SharesFundSerializer(fund).data)


class CommunitySharesContributeView(APIView):
    """
    DISABLED: All shares contributions must go through M-Pesa STK push.
    Use POST /api/mpesa/stk-push/ with payment_type='shares' instead.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, community_id):
        return Response(
            {"error": "Direct shares contributions are disabled. Use M-Pesa STK push (payment_type='shares')."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )


class WelfareClaimVoteView(APIView):
    """Admin-only: approve or reject a pending welfare claim."""
    permission_classes = [IsAuthenticated]

    def post(self, request, claim_id):
        action = request.data.get('action', 'approve').lower()
        if action not in ('approve', 'reject'):
            return Response({"error": "action must be approve or reject"}, status=status.HTTP_400_BAD_REQUEST)
        if action == 'reject':
            claim = WelfareService.reject_claim(claim_id, request.user)
        else:
            claim = WelfareService.approve_claim(claim_id, request.user)
        return Response(WelfareClaimSerializer(claim).data)


# ---------------------------------------------------------------------------
# Community-scoped welfare (legacy / backwards compat)
# ---------------------------------------------------------------------------

class WelfareFundView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, community_id):
        from apps.communities.models import Community
        community = get_object_or_404(Community, id=community_id)
        fund = WelfareService.get_or_create_community_fund(community)
        return Response(WelfareFundSerializer(fund).data)

    def patch(self, request, community_id):
        from apps.communities.models import Community, CommunityMembership
        community = get_object_or_404(Community, id=community_id)
        is_admin = CommunityMembership.objects.filter(
            community=community, user=request.user,
            role__in=['admin', 'treasurer'], is_active=True,
        ).exists()
        if not is_admin:
            return Response({"error": "Admins only"}, status=status.HTTP_403_FORBIDDEN)
        fund = WelfareService.get_or_create_community_fund(community)
        monthly = request.data.get('monthly_contribution')
        if monthly:
            fund.monthly_contribution = monthly
            fund.save()
        return Response(WelfareFundSerializer(fund).data)


class WelfareContributeView(APIView):
    """
    Called internally by the M-Pesa STK callback after a successful welfare payment.
    Direct POST from the mobile client is disabled — use M-Pesa STK push instead.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, community_id):
        return Response(
            {"error": "Direct welfare contributions are disabled. Use M-Pesa STK push (payment_type='welfare')."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )


class WelfareClaimListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def _check_membership(self, community, user):
        """Return True if user is a member or creator of the community."""
        from apps.communities.models import CommunityMembership
        if community.created_by == user:
            return True
        return CommunityMembership.objects.filter(
            community=community, user=user, is_active=True
        ).exists()

    def get(self, request, community_id):
        from apps.communities.models import Community
        community = get_object_or_404(Community, id=community_id)
        if not self._check_membership(community, request.user):
            return Response({"error": "You must be a community member to view welfare claims."}, status=status.HTTP_403_FORBIDDEN)
        fund = WelfareFund.objects.filter(community=community).first()
        if not fund:
            return Response([])
        claims = fund.claims.select_related('claimant').prefetch_related(
            'votes__voter'
        ).order_by('-created_at')
        paginator = FinancialCursorPagination()
        page = paginator.paginate_queryset(claims, request)
        return paginator.get_paginated_response(
            WelfareClaimSerializer(page, many=True).data
        )

    def post(self, request, community_id):
        amount = request.data.get('amount_requested')
        reason = request.data.get('reason', '')
        if not amount or not reason:
            return Response({"error": "amount_requested and reason are required"}, status=status.HTTP_400_BAD_REQUEST)
        from apps.communities.models import Community
        community = get_object_or_404(Community, id=community_id)
        if not self._check_membership(community, request.user):
            return Response({"error": "You must be a community member to submit a welfare claim."}, status=status.HTTP_403_FORBIDDEN)
        fund = WelfareService.get_or_create_community_fund(community)
        claim = WelfareService.submit_claim(fund.id, request.user, amount, reason)
        return Response(WelfareClaimSerializer(claim).data, status=status.HTTP_201_CREATED)


class WelfareActivityView(APIView):
    """
    Returns a unified activity log for the welfare fund:
    - DEPOSIT  — member contributions
    - WITHDRAWAL — approved/disbursed claims
    Sorted newest first.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, community_id):
        from apps.communities.models import Community
        community = get_object_or_404(Community, id=community_id)
        fund = WelfareFund.objects.filter(community=community).first()
        if not fund:
            return Response([])

        activity = []

        # Contributions (deposits)
        for c in fund.contributions.select_related('user').order_by('-created_at'):
            activity.append({
                "type":          "DEPOSIT",
                "amount":        str(c.amount),
                "phone":         c.user.phone_number,
                "name":          getattr(c.user, 'name', c.user.phone_number),
                "mpesa_receipt": None,
                "note":          "Welfare contribution",
                "date":          c.created_at.isoformat(),
            })

        # Claim disbursements (withdrawals — approved or disbursed)
        for cl in fund.claims.filter(
            status__in=['APPROVED', 'DISBURSED']
        ).select_related('claimant').order_by('-approved_at'):
            activity.append({
                "type":          "WITHDRAWAL",
                "amount":        str(cl.amount_requested),
                "phone":         cl.claimant.phone_number,
                "name":          getattr(cl.claimant, 'name', cl.claimant.phone_number),
                "mpesa_receipt": cl.mpesa_receipt,
                "note":          cl.reason,
                "date":          (cl.disbursed_at or cl.approved_at).isoformat(),
                "status":        cl.status,
            })

        activity.sort(key=lambda x: x["date"], reverse=True)
        return Response(activity)


# ---------------------------------------------------------------------------
# Emergency Advances
# ---------------------------------------------------------------------------

class AdvanceListCreateView(APIView):
    permission_classes = [IsAuthenticated]

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
        return Response(EmergencyAdvanceSerializer(advance).data, status=status.HTTP_201_CREATED)


class AdvanceActionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, advance_id):
        action = request.data.get('action', '').lower()
        if action == 'approve':
            advance = EmergencyAdvanceService.approve_advance(advance_id, request.user)
        elif action == 'reject':
            advance = EmergencyAdvanceService.reject_advance(advance_id, request.user)
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
    permission_classes = [IsAuthenticated]

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

class StandingOrderListCreateView(APIView):
    permission_classes = [IsAuthenticated]

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
    permission_classes = [IsAuthenticated]

    def post(self, request, order_id):
        order = StandingOrderService.execute_standing_order(order_id, request.user)
        return Response(StandingOrderSerializer(order).data)


class StandingOrderCancelView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, order_id):
        order = StandingOrderService.cancel_standing_order(order_id, request.user)
        return Response(StandingOrderSerializer(order).data)


class StandingOrderUpdateView(APIView):
    """PATCH standing-orders/<order_id>/update/ — amend amount, frequency, or fixed_payee_phone."""
    permission_classes = [IsAuthenticated]

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

class AmendmentListCreateView(APIView):
    """
    GET  /contributions/<id>/amendments/ — list all amendments for a contribution
    POST /contributions/<id>/amendments/ — propose a new amendment (admin/creator only)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, contribution_id):
        contribution = get_object_or_404(Contribution, id=contribution_id)
        denied = _member_only(contribution, request.user)
        if denied:
            return denied
        amendments = AmendmentService.get_amendments(contribution_id)
        return Response(ContributionAmendmentSerializer(amendments, many=True).data)

    def post(self, request, contribution_id):
        changes = request.data.get('changes', {})
        reason  = request.data.get('reason', '')
        if not isinstance(changes, dict) or not changes:
            return Response({"error": "'changes' must be a non-empty object of field→value pairs."},
                            status=status.HTTP_400_BAD_REQUEST)
        amendment = AmendmentService.propose(contribution_id, request.user, changes, reason)
        return Response(ContributionAmendmentSerializer(amendment).data, status=status.HTTP_201_CREATED)


class AmendmentVoteView(APIView):
    """POST /contributions/amendments/<amendment_id>/vote/ — cast APPROVE or REJECT."""
    permission_classes = [IsAuthenticated]

    def post(self, request, amendment_id):
        vote_choice = request.data.get('vote', '').upper()
        if vote_choice not in ('APPROVE', 'REJECT'):
            return Response({"error": "vote must be APPROVE or REJECT"}, status=status.HTTP_400_BAD_REQUEST)
        amendment = AmendmentService.vote(amendment_id, request.user, vote_choice)
        return Response(ContributionAmendmentSerializer(amendment).data)


class AmendmentWithdrawView(APIView):
    """POST /contributions/amendments/<amendment_id>/withdraw/ — proposer retracts their proposal."""
    permission_classes = [IsAuthenticated]

    def post(self, request, amendment_id):
        amendment = AmendmentService.withdraw(amendment_id, request.user)
        return Response(ContributionAmendmentSerializer(amendment).data)


# ---------------------------------------------------------------------------
# Contribution Join Requests & Invitations
# ---------------------------------------------------------------------------

class ContributionJoinRequestListView(APIView):
    """
    GET  /contributions/<id>/join-requests/  — list pending requests (admins only)
    POST /contributions/<id>/join-requests/  — member submits a join request
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, contribution_id):
        contribution = get_object_or_404(Contribution, id=contribution_id)
        # Only creator/admins can see the queue
        is_admin = contribution.created_by == request.user
        if not is_admin and contribution.community:
            from apps.communities.models import CommunityMembership
            is_admin = CommunityMembership.objects.filter(
                community=contribution.community, user=request.user,
                role__in=['admin', 'treasurer'], is_active=True,
            ).exists()
        if not is_admin:
            return Response({"error": "Only admins can view join requests."}, status=status.HTTP_403_FORBIDDEN)
        requests = ContributionJoinRequestService.get_pending_requests(contribution_id)
        return Response(ContributionJoinRequestSerializer(requests, many=True).data)

    def post(self, request, contribution_id):
        jr = ContributionJoinRequestService.request_join(contribution_id, request.user)
        return Response(ContributionJoinRequestSerializer(jr).data, status=status.HTTP_201_CREATED)


class ContributionJoinRequestActionView(APIView):
    """POST /contributions/join-requests/<id>/action/ — admin approves or rejects a REQUEST."""
    permission_classes = [IsAuthenticated]

    def post(self, request, request_id):
        action = request.data.get('action', '').lower()
        if action not in ('approve', 'reject'):
            return Response({"error": "action must be 'approve' or 'reject'."}, status=status.HTTP_400_BAD_REQUEST)
        jr = ContributionJoinRequestService.action_request(request_id, request.user, action)
        return Response(ContributionJoinRequestSerializer(jr).data)


class ContributionInviteView(APIView):
    """POST /contributions/<id>/invite/ — admin invites a community member."""
    permission_classes = [IsAuthenticated]

    def post(self, request, contribution_id):
        phone = request.data.get('phone', '').strip()
        if not phone:
            return Response({"error": "'phone' is required."}, status=status.HTTP_400_BAD_REQUEST)
        jr = ContributionJoinRequestService.invite_user(contribution_id, request.user, phone)
        return Response(ContributionJoinRequestSerializer(jr).data, status=status.HTTP_201_CREATED)


class ContributionInviteRespondView(APIView):
    """POST /contributions/invitations/<id>/respond/ — invitee accepts or declines."""
    permission_classes = [IsAuthenticated]

    def post(self, request, request_id):
        action = request.data.get('action', '').lower()
        if action not in ('accept', 'decline'):
            return Response({"error": "action must be 'accept' or 'decline'."}, status=status.HTTP_400_BAD_REQUEST)
        jr = ContributionJoinRequestService.respond_to_invite(request_id, request.user, action)
        return Response(ContributionJoinRequestSerializer(jr).data)


class MyContributionJoinRequestView(APIView):
    """GET /contributions/<id>/my-join-request/ — return the current user's REQUEST row."""
    permission_classes = [IsAuthenticated]

    def get(self, request, contribution_id):
        jr = ContributionJoinRequestService.get_my_request(contribution_id, request.user)
        if not jr:
            return Response(None)
        return Response(ContributionJoinRequestSerializer(jr).data)


class MyContributionInviteView(APIView):
    """GET /contributions/<id>/my-invite/ — return a pending INVITE for the current user."""
    permission_classes = [IsAuthenticated]

    def get(self, request, contribution_id):
        jr = ContributionJoinRequestService.get_my_invite(contribution_id, request.user)
        if not jr:
            return Response(None)
        return Response(ContributionJoinRequestSerializer(jr).data)
