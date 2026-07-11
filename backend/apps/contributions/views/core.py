from ._common import *  # shared imports + helpers (ADR-0013)


class ContributionCreateView(APIView):
    permission_classes = [IsActiveSession]

    def post(self, request):
        member_phones   = request.data.get('member_phones', [])
        add_all_members = bool(request.data.get('add_all_members', False))
        share_price     = request.data.get('share_price')

        serializer = ContributionSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        community = serializer.validated_data.get('community')
        if community:
            from apps.communities.models import Community as CommunityModel

            perm = community.contribution_permission
            if (perm == CommunityModel.ContributionPermission.ADMINS
                    and not can(request.user, "community.finance.manage", community)):
                return Response(
                    {"error": "Only admins and treasurers can create contributions in this community."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if (perm == CommunityModel.ContributionPermission.MEMBERS
                    and not can(request.user, "community.view", community)):
                return Response(
                    {"error": "You must be a member of this community to create a contribution."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        contribution = ContributionService.create_contribution(
            request.user,
            serializer.validated_data,
            member_phones=member_phones,
            add_all_members=add_all_members,
        )
        logger.info(
            "ContributionCreateView: user %s created contribution %s ('%s')",
            request.user.id, contribution.id, contribution.title,
        )
        return Response(
            ContributionSerializer(contribution, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )




class MyContributionsView(APIView):
    permission_classes = [IsActiveSession]

    def get(self, request):
        active = request.query_params.get('active', 'true').lower() != 'false'
        contributions = ContributionService.get_user_contributions(request.user, active_only=active)
        paginator = FinancialCursorPagination()
        page = paginator.paginate_queryset(contributions, request)
        return paginator.get_paginated_response(
            ContributionSerializer(page, many=True, context={'request': request}).data
        )


class CommunityContributionsView(APIView):
    permission_classes = [IsActiveSession]

    def get(self, request, community_id):
        from django.db.models import Count, Q
        from apps.communities.models import Community
        from apps.ledger.balances import user_fund_balances

        community = get_object_or_404(Community, id=community_id)
        if not can(request.user, "community.view", community):
            logger.warning(
                "CommunityContributionsView: user %s attempted to list contributions "
                "for community %s without membership",
                request.user.id, community_id,
            )
            return Response(
                {"error": "You must be a member of this community to view its contributions."},
                status=status.HTTP_403_FORBIDDEN,
            )

        contributions = Contribution.objects.filter(
            community_id=community_id, is_active=True
        ).annotate(
            active_participant_count=Count(
                'participants', filter=Q(participants__is_active=True), distinct=True
            )
        ).order_by('-created_at')
        paginator = FinancialCursorPagination()
        page = paginator.paginate_queryset(contributions, request)
        user_balances = user_fund_balances(
            request.user, 'contribution', [c.id for c in page])
        return paginator.get_paginated_response(
            ContributionSerializer(page, many=True, context={
                'request': request, 'user_balances': user_balances}).data
        )


class OpenContributionsView(APIView):
    permission_classes = [IsActiveSession]

    def get(self, request):
        from django.db.models import Count, Q
        from apps.ledger.balances import user_fund_balances
        contributions = Contribution.objects.filter(
            visibility='open', is_active=True
        ).annotate(
            active_participant_count=Count(
                'participants', filter=Q(participants__is_active=True), distinct=True
            )
        ).order_by('-created_at')
        paginator = FinancialCursorPagination()
        page = paginator.paginate_queryset(contributions, request)
        user_balances = user_fund_balances(
            request.user, 'contribution', [c.id for c in page])
        return paginator.get_paginated_response(
            ContributionSerializer(page, many=True, context={
                'request': request, 'user_balances': user_balances}).data
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
    permission_classes = [IsActiveSession]

    def get(self, request):
        from django.db.models import Count, Q
        from django.utils import timezone

        q = request.query_params.get('q', '').strip()
        try:
            limit  = min(int(request.query_params.get('limit',  30)), 100)
            offset = int(request.query_params.get('offset', 0))
        except (ValueError, TypeError):
            return Response(
                {"error": "limit and offset must be integers."},
                status=status.HTTP_400_BAD_REQUEST,
            )

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

        from apps.ledger.balances import fund_balances
        pool_by_id = fund_balances('contribution', [c.id for c in campaigns])

        results = []
        for c in campaigns:
            target  = float(c.target_amount) if c.target_amount else None
            current = float(pool_by_id.get(c.id, 0))
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
    permission_classes = [IsActiveSession]

    def get(self, request, contribution_id):
        c = get_object_or_404(Contribution, id=contribution_id)

        # Participants and the creator always get the full detail view.
        if _is_contribution_member(c, request.user):
            return Response(ContributionSerializer(c, context={'request': request}).data)

        # Non-participant: determine whether they can reach the request-to-join screen.
        if c.visibility == 'closed' and c.community:
            if not can(request.user, "community.view", c.community):
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
    permission_classes = [IsActiveSession]

    def get(self, request, invite_code):
        c = ContributionService.get_by_invite_code(invite_code)
        if not c:
            return Response({"error": "Invalid invite code"}, status=status.HTTP_404_NOT_FOUND)
        return Response(ContributionSerializer(c, context={'request': request}).data)


class JoinContributionView(APIView):
    permission_classes = [IsActiveSession]

    def post(self, request, contribution_id):
        participant = ContributionService.join_contribution(contribution_id, request.user)
        logger.info(
            "JoinContributionView: user %s joined contribution %s",
            request.user.id, contribution_id,
        )
        return Response(ContributionParticipantSerializer(participant).data)


class LeaveContributionView(APIView):
    permission_classes = [IsActiveSession]

    def post(self, request, contribution_id):
        ContributionService.leave_contribution(contribution_id, request.user)
        logger.info(
            "LeaveContributionView: user %s left contribution %s",
            request.user.id, contribution_id,
        )
        return Response({"message": "Left successfully"})


class ContributionCloseView(APIView):
    permission_classes = [IsActiveSession]

    def post(self, request, contribution_id):
        c = ContributionService.close_contribution(contribution_id, request.user)
        logger.info("ContributionCloseView: user %s closed contribution %s", request.user.id, contribution_id)
        return Response(ContributionSerializer(c, context={'request': request}).data)


class ContributionReopenView(APIView):
    permission_classes = [IsActiveSession]

    def post(self, request, contribution_id):
        c = ContributionService.reopen_contribution(contribution_id, request.user)
        return Response(ContributionSerializer(c, context={'request': request}).data)


class ContributionArchiveView(APIView):
    permission_classes = [IsActiveSession]

    def post(self, request, contribution_id):
        c = ContributionService.archive_contribution(contribution_id, request.user)
        logger.info("ContributionArchiveView: user %s archived contribution %s", request.user.id, contribution_id)
        return Response(ContributionSerializer(c, context={'request': request}).data)


class ContributionUpdateView(APIView):
    """
    PATCH /contributions/<contribution_id>/update/
    Direct (immediate) edit — only cosmetic fields: title and description.
    Sensitive field changes (fixed_amount, target_amount, voting_threshold,
    end_date, period_months, visibility) must go through an amendment proposal.
    """
    permission_classes = [IsActiveSession]
    DIRECT_FIELDS = {'title', 'description'}

    def patch(self, request, contribution_id):
        contribution = get_object_or_404(Contribution, id=contribution_id)

        if not can(request.user, "contribution.admin", contribution):
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
    permission_classes = [IsActiveSession]

    def delete(self, request, contribution_id):
        ContributionService.delete_contribution(contribution_id, request.user)
        logger.info("ContributionDeleteView: user %s deleted contribution %s", request.user.id, contribution_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ContributionParticipantsView(APIView):
    permission_classes = [IsActiveSession]

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
    permission_classes = [IsActiveSession]

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
    permission_classes = [IsActiveSession]

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

    Section C — transaction_visibility:
      all        → all participants see all transactions
      own        → each member sees only their own
      admins_all → admins see all; members see their own only
    """
    permission_classes = [IsActiveSession]

    def get(self, request, contribution_id):
        contribution = get_object_or_404(Contribution, id=contribution_id)

        if not can(request.user, "contribution.participate", contribution):
            return Response(
                {"error": "You are not a participant in this contribution."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Determine whether this user can see everyone's transactions
        vis = contribution.transaction_visibility
        see_all = (
            vis == 'all' or
            (vis == 'admins_all' and can(request.user, "contribution.admin", contribution))
        )

        txs = ContributionTransaction.objects.filter(
            contribution=contribution,
            **({}  if see_all else {'user': request.user}),
        ).select_related('user', 'contribution').order_by('-created_at')
        paginator = FinancialCursorPagination()
        page = paginator.paginate_queryset(txs, request)
        return paginator.get_paginated_response(
            ContributionTransactionSerializer(page, many=True, context={'request': request}).data
        )


# ---------------------------------------------------------------------------
# ROSCA
# ---------------------------------------------------------------------------
