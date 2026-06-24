"""Global search endpoint (ADR-0017)."""
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.auth import IsActiveSession

from .services import SearchService, TYPES


class SearchView(APIView):
    """GET /api/search/?q=<query>&type=<all|communities|contributions|users>&limit=N"""
    permission_classes = [IsActiveSession]

    def get(self, request):
        q = request.query_params.get('q', '')
        type_param = (request.query_params.get('type') or 'all').strip()
        types = TYPES if type_param in ('', 'all') else tuple(
            t for t in type_param.split(',') if t in TYPES)
        results = SearchService.search(
            request.user, q, types=types or None,
            limit=request.query_params.get('limit') or 20,
        )
        return Response({'query': q.strip(), 'results': results})
