from ._common import *  # shared imports + helpers (ADR-0013)


class ROSCARotationView(APIView):
    permission_classes = [IsActiveSession]

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
    permission_classes = [IsActiveSession]

    def post(self, request, contribution_id):
        slot = ROSCAService.mark_slot_paid(contribution_id, request.user)
        return Response(ROSCASlotSerializer(slot).data)


# ---------------------------------------------------------------------------
# Disbursement
# ---------------------------------------------------------------------------
