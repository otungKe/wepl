from ._common import *  # shared imports + helpers (ADR-0013 view split)


class AmendmentListCreateView(APIView):
    """
    GET  /contributions/<id>/amendments/ — list all amendments for a contribution
    POST /contributions/<id>/amendments/ — propose a new amendment (admin/creator only)
    """
    permission_classes = [IsActiveSession]

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
    permission_classes = [IsActiveSession]

    def post(self, request, amendment_id):
        vote_choice = request.data.get('vote', '').upper()
        if vote_choice not in ('APPROVE', 'REJECT'):
            return Response({"error": "vote must be APPROVE or REJECT"}, status=status.HTTP_400_BAD_REQUEST)
        amendment = AmendmentService.vote(amendment_id, request.user, vote_choice)
        return Response(ContributionAmendmentSerializer(amendment).data)


class AmendmentWithdrawView(APIView):
    """POST /contributions/amendments/<amendment_id>/withdraw/ — proposer retracts their proposal."""
    permission_classes = [IsActiveSession]

    def post(self, request, amendment_id):
        amendment = AmendmentService.withdraw(amendment_id, request.user)
        return Response(ContributionAmendmentSerializer(amendment).data)


# ---------------------------------------------------------------------------
# Contribution Join Requests & Invitations
# ---------------------------------------------------------------------------
