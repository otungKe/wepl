import logging

from rest_framework.pagination import CursorPagination
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from apps.users.auth import IsActiveSession

from .models import Activity
from .render import render_activity
from .serializers import ActivitySerializer

logger = logging.getLogger(__name__)


class ActivityCursorPagination(CursorPagination):
    """Keyset cursor pagination for the append-heavy activity feed (ADR-0016):
    stable under concurrent inserts, no total-count leak. Used by the versioned
    /api/v2/ feed only — the legacy feed keeps offset pagination (see below)."""
    ordering              = ('-created_at', '-id')
    page_size             = 50
    page_size_query_param = 'page_size'
    max_page_size         = 200


def _personalize(activity, user) -> str:
    """Render the activity, then swap the actor's own name for 'You' on their
    personal feed. Rendering happens at read time from typed params (ADR-0016)."""
    message = render_activity(activity)
    if activity.user_id != user.id:
        return message
    display = (getattr(user, 'name', '') or '').strip() or user.phone_number
    for prefix in ([display, user.phone_number] if display != user.phone_number else [user.phone_number]):
        if message.startswith(prefix):
            return 'You' + message[len(prefix):]
    return message


class _ActivityFeedBase(APIView):
    """Shared query-building for the activity feed.

    Two endpoints expose this data with different pagination *shapes*:
      - ``ActivityFeedView`` (legacy, /api/ + /api/v1/): offset pagination,
        ``{count, results, has_more}`` — the contract shipped mobile binaries
        depend on. Kept stable per ADR-0021.
      - ``ActivityFeedViewV2`` (/api/v2/): keyset cursor pagination,
        ``{next, previous, results}``.

    The typed-event rendering (ADR-0016) and the visibility rule are identical
    for both; only the pagination differs.
    """
    permission_classes = [IsActiveSession]

    def _feed_queryset(self, request):
        """Return ``(queryset, None)`` or ``(None, error_response)``.

        Without ``?community`` → the caller's own activity (personal feed). With
        ``?community=<id>`` → activity visible to the caller within that community
        (ADR-0016); a non-member sees nothing. An optional
        ``?type=`` substring filter applies to either.
        """
        activity_type = request.query_params.get('type')
        community_id  = request.query_params.get('community')

        if community_id:
            try:
                community_id = int(community_id)
            except (TypeError, ValueError):
                return None, Response(
                    {"error": "community must be an integer id."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            qs = Activity.objects.visible_to(request.user).filter(community_id=community_id)
        else:
            qs = Activity.objects.filter(user=request.user)

        qs = qs.select_related('user').order_by('-created_at', '-id')

        if activity_type:
            # icontains so "contribution" matches contribution_payment, etc.
            qs = qs.filter(activity_type__icontains=activity_type)

        return qs, None


class ActivityFeedView(_ActivityFeedBase):
    """
    GET /api/activity/  (and /api/v1/activity/) — **legacy** offset feed.

    Query params:
      type       — substring filter on activity_type (e.g. ?type=contribution)
      community  — scope to a community feed (visibility-filtered to members)
      limit      — max records, default 50, max 200
      offset     — pagination offset

    Response shape ``{count, results, has_more}`` is preserved for shipped mobile
    binaries (ADR-0021). New clients should use the cursor feed at /api/v2/.
    """

    def get(self, request):
        qs, error = self._feed_queryset(request)
        if error is not None:
            return error

        try:
            limit  = min(int(request.query_params.get('limit',  50)), 200)
            offset = int(request.query_params.get('offset', 0))
        except (ValueError, TypeError):
            return Response(
                {"error": "limit and offset must be integers."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        total = qs.count()
        page  = list(qs[offset: offset + limit])
        for a in page:
            a.message = _personalize(a, request.user)

        logger.info(
            "ActivityFeedView: user %s fetched feed (type=%s community=%s limit=%d offset=%d)",
            request.user.id, request.query_params.get('type') or '*',
            request.query_params.get('community') or '-', limit, offset,
        )

        serializer = ActivitySerializer(page, many=True)
        return Response({
            'count':    total,
            'results':  serializer.data,
            'has_more': (offset + limit) < total,
        })


class ActivityFeedViewV2(_ActivityFeedBase):
    """
    GET /api/v2/activity/ — cursor-paginated feed (ADR-0016).

    Same data and visibility rule as the legacy feed, but keyset-cursor
    paginated: query params ``type``, ``community``, ``page_size`` (max 200) and
    ``cursor``; response shape ``{next, previous, results}``. This is the
    breaking pagination change deliberately kept off the legacy/v1 path (ADR-0021).
    """

    def get(self, request):
        qs, error = self._feed_queryset(request)
        if error is not None:
            return error

        paginator = ActivityCursorPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        for a in page:
            a.message = _personalize(a, request.user)

        logger.info(
            "ActivityFeedViewV2: user %s fetched feed (type=%s community=%s)",
            request.user.id, request.query_params.get('type') or '*',
            request.query_params.get('community') or '-',
        )

        serializer = ActivitySerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)
