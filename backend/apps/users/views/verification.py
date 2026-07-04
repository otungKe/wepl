from django.utils import timezone

from ._common import *  # shared imports/helpers (ADR-0013 view split)
from ..models import VerificationRequest
from ..serializers import VerificationRequestSerializer, VerificationRespondSerializer


class VerificationRequestListView(APIView):
    """GET /api/users/verification-requests/ — the current user's ongoing
    verification requests (open + submitted + recently resolved), newest first.
    Backs the mobile Verification Center's "Requests & documents" section."""
    permission_classes = [IsActiveSession]

    def get(self, request):
        qs = VerificationRequest.objects.filter(user=request.user)
        return Response(VerificationRequestSerializer(qs, many=True).data)


class VerificationRequestRespondView(APIView):
    """POST /api/users/verification-requests/<id>/respond/ — the user answers an
    open request with a note and/or a document. Moves it to 'submitted' so the
    compliance team can review."""
    permission_classes = [IsActiveSession]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, pk):
        try:
            req = VerificationRequest.objects.get(pk=pk, user=request.user)
        except VerificationRequest.DoesNotExist:
            return Response({"error": "Request not found."}, status=status.HTTP_404_NOT_FOUND)

        if req.status != VerificationRequest.Status.OPEN:
            return Response(
                {"error": "This request has already been answered."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = VerificationRespondSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        req.response_note = serializer.validated_data.get('response_note', '')
        if serializer.validated_data.get('document'):
            req.document = serializer.validated_data['document']
        req.status = VerificationRequest.Status.SUBMITTED
        req.responded_at = timezone.now()
        req.save(update_fields=['response_note', 'document', 'status', 'responded_at'])

        logger.info("VerificationRequest %s answered by user %s", req.id, request.user.id)
        return Response(VerificationRequestSerializer(req).data)
