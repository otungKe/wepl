"""File upload + signed download endpoints (ADR-0018)."""
import logging

from django.core.exceptions import ValidationError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.views import APIView

from apps.users.auth import IsActiveSession

from .models import StoredFile
from .serializers import StoredFileSerializer
from .services import FileService
from .signing import read_token

logger = logging.getLogger(__name__)


class FileUploadView(APIView):
    """POST /api/files/  (multipart: file=<binary>, kind=<kind>)"""
    permission_classes = [IsActiveSession]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        uploaded = request.FILES.get('file')
        kind = (request.data.get('kind') or '').strip()
        if not uploaded:
            return Response({"error": "file is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            stored = FileService.save(owner=request.user, kind=kind, uploaded_file=uploaded)
        except ValidationError as e:
            msg = e.messages[0] if hasattr(e, 'messages') else str(e)
            return Response({"error": msg}, status=status.HTTP_400_BAD_REQUEST)
        return Response(StoredFileSerializer(stored).data, status=status.HTTP_201_CREATED)


class FileDownloadView(APIView):
    """GET /api/files/<id>/download/?token=<signed>

    The signed, time-limited token is the capability — no session required, so
    <img src> works. Infected or soft-deleted files are not served.
    """
    permission_classes = [AllowAny]

    def get(self, request, file_id):
        token = request.query_params.get('token', '')
        if read_token(token) != str(file_id):
            return Response({"error": "Invalid or expired link."}, status=status.HTTP_403_FORBIDDEN)

        stored = get_object_or_404(StoredFile, id=file_id)
        if not stored.is_available:
            raise Http404("File not available.")
        try:
            fh = stored.file.open('rb')
        except Exception:
            raise Http404("File not available.")
        resp = FileResponse(fh, content_type=stored.content_type or 'application/octet-stream')
        resp['Content-Disposition'] = f'inline; filename="{stored.original_name or stored.id}"'
        return resp
