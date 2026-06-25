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
    stable under concurrent inserts, no total-count leak."""
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


class ActivityFeedView(APIView):
    """
    GET /api/activity/
    Query params:
      type       — substring filter on activity_type (e.g. ?type=contribution)
      community  — scope to a community feed (visibility-filtered to members)
      page_size  — page size, default 50, max 200
      cursor     — opaque keyset cursor (from next/previous links)

    Without ?community, returns the caller's own activity. With ?community=<id>,
    returns activity visible to the caller within that community (ADR-0016
    visibility rule). Either way, rows the caller may not see are never returned.
    """
    permission_classes = [IsActiveSession]

    def get(self, request):
        activity_type = request.query_params.get('type')
        community_id  = request.query_params.get('community')

        if community_id:
            try:
                community_id = int(community_id)
            except (TypeError, ValueError):
                return Response(
                    {"error": "community must be an integer id."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # Visibility-filtered to what the caller may see, then scoped to the
            # community — a non-member sees nothing here.
            qs = Activity.objects.visible_to(request.user).filter(community_id=community_id)
        else:
            # Personal feed: the caller's own activity.
            qs = Activity.objects.filter(user=request.user)

        qs = qs.select_related('user').order_by('-created_at', '-id')

        if activity_type:
            # icontains so "contribution" matches contribution_payment, etc.
            qs = qs.filter(activity_type__icontains=activity_type)

        paginator = ActivityCursorPagination()
        page = paginator.paginate_queryset(qs, request, view=self)

        for a in page:
            a.message = _personalize(a, request.user)

        logger.info(
            "ActivityFeedView: user %s fetched feed (type=%s community=%s)",
            request.user.id, activity_type or '*', community_id or '-',
        )

        serializer = ActivitySerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)
