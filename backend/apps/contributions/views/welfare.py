from ._common import *  # shared imports + helpers (ADR-0013 view split)


class WelfareClaimVoteView(APIView):
    """Admin-only: approve or reject a pending welfare claim."""
    permission_classes = [IsActiveSession]

    def post(self, request, claim_id):
        action = request.data.get('action', 'approve').lower()
        if action not in ('approve', 'reject'):
            return Response({"error": "action must be approve or reject"}, status=status.HTTP_400_BAD_REQUEST)
        if action == 'reject':
            claim = WelfareService.reject_claim(claim_id, request.user)
        else:
            claim = WelfareService.approve_claim(claim_id, request.user)
        logger.info(
            "WelfareClaimVoteView: user %s %sd welfare claim %s",
            request.user.id, action, claim_id,
        )
        return Response(WelfareClaimSerializer(claim).data)


# ---------------------------------------------------------------------------
# Community-scoped welfare (legacy / backwards compat)
# ---------------------------------------------------------------------------

class WelfareFundView(APIView):
    permission_classes = [IsActiveSession]

    def get(self, request, community_id):
        from apps.communities.models import Community
        community = get_object_or_404(Community, id=community_id)
        fund = WelfareService.get_or_create_community_fund(community)
        return Response(WelfareFundSerializer(fund).data)

    def patch(self, request, community_id):
        from apps.communities.models import Community
        community = get_object_or_404(Community, id=community_id)
        if not can(request.user, "community.finance.manage", community):
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
    permission_classes = [IsActiveSession]

    def post(self, request, community_id):
        return Response(
            {"error": "Direct welfare contributions are disabled. Use M-Pesa STK push (payment_type='welfare')."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )


class WelfareClaimListCreateView(APIView):
    permission_classes = [IsActiveSession]

    def _check_membership(self, community, user):
        """Return True if user is a member or creator of the community (ADR-0009)."""
        return can(user, "community.view", community)

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
        logger.info(
            "WelfareClaimListCreateView: user %s submitted welfare claim %s "
            "for KES %s in community %s",
            request.user.id, claim.id, amount, community_id,
        )
        return Response(WelfareClaimSerializer(claim).data, status=status.HTTP_201_CREATED)


class WelfareActivityView(APIView):
    """
    Returns a unified activity log for the welfare fund:
    - DEPOSIT  — member contributions
    - WITHDRAWAL — approved/disbursed claims
    Sorted newest first.
    """
    permission_classes = [IsActiveSession]

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
