from ._common import *  # shared imports + helpers (ADR-0013)


class ContributionJoinRequestListView(APIView):
    """
    GET  /contributions/<id>/join-requests/  — list pending requests (admins only)
    POST /contributions/<id>/join-requests/  — member submits a join request
    """
    permission_classes = [IsActiveSession]

    def get(self, request, contribution_id):
        contribution = get_object_or_404(Contribution, id=contribution_id)
        # Only creator/admins can see the queue
        if not can(request.user, "contribution.admin", contribution):
            return Response({"error": "Only admins can view join requests."}, status=status.HTTP_403_FORBIDDEN)
        requests = ContributionJoinRequestService.get_pending_requests(contribution_id)
        return Response(ContributionJoinRequestSerializer(requests, many=True).data)

    def post(self, request, contribution_id):
        jr = ContributionJoinRequestService.request_join(contribution_id, request.user)
        logger.info(
            "ContributionJoinRequestListView: user %s submitted join request %s "
            "for contribution %s",
            request.user.id, jr.id, contribution_id,
        )
        return Response(ContributionJoinRequestSerializer(jr).data, status=status.HTTP_201_CREATED)


class ContributionJoinRequestActionView(APIView):
    """POST /contributions/join-requests/<id>/action/ — admin approves or rejects a REQUEST."""
    permission_classes = [IsActiveSession]

    def post(self, request, request_id):
        action = request.data.get('action', '').lower()
        if action not in ('approve', 'reject'):
            return Response({"error": "action must be 'approve' or 'reject'."}, status=status.HTTP_400_BAD_REQUEST)
        jr = ContributionJoinRequestService.action_request(request_id, request.user, action)
        logger.info(
            "ContributionJoinRequestActionView: user %s %sd join request %s",
            request.user.id, action, request_id,
        )
        return Response(ContributionJoinRequestSerializer(jr).data)


class ContributionInviteView(APIView):
    """POST /contributions/<id>/invite/ — admin invites a community member."""
    permission_classes = [IsActiveSession]

    def post(self, request, contribution_id):
        phone = request.data.get('phone', '').strip()
        if not phone:
            return Response({"error": "'phone' is required."}, status=status.HTTP_400_BAD_REQUEST)
        jr = ContributionJoinRequestService.invite_user(contribution_id, request.user, phone)
        logger.info(
            "ContributionInviteView: user %s invited %s to contribution %s (invite %s)",
            request.user.id, phone, contribution_id, jr.id,
        )
        return Response(ContributionJoinRequestSerializer(jr).data, status=status.HTTP_201_CREATED)


class ContributionInviteRespondView(APIView):
    """POST /contributions/invitations/<id>/respond/ — invitee accepts or declines."""
    permission_classes = [IsActiveSession]

    def post(self, request, request_id):
        action = request.data.get('action', '').lower()
        if action not in ('accept', 'decline'):
            return Response({"error": "action must be 'accept' or 'decline'."}, status=status.HTTP_400_BAD_REQUEST)
        jr = ContributionJoinRequestService.respond_to_invite(request_id, request.user, action)
        logger.info(
            "ContributionInviteRespondView: user %s %sd invitation %s",
            request.user.id, action, request_id,
        )
        return Response(ContributionJoinRequestSerializer(jr).data)


class MyContributionJoinRequestView(APIView):
    """GET /contributions/<id>/my-join-request/ — return the current user's REQUEST row."""
    permission_classes = [IsActiveSession]

    def get(self, request, contribution_id):
        jr = ContributionJoinRequestService.get_my_request(contribution_id, request.user)
        if not jr:
            return Response(None)
        return Response(ContributionJoinRequestSerializer(jr).data)


class MyContributionInviteView(APIView):
    """GET /contributions/<id>/my-invite/ — return a pending INVITE for the current user."""
    permission_classes = [IsActiveSession]

    def get(self, request, contribution_id):
        jr = ContributionJoinRequestService.get_my_invite(contribution_id, request.user)
        if not jr:
            return Response(None)
        return Response(ContributionJoinRequestSerializer(jr).data)
