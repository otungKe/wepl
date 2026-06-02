import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from apps.users.auth import IsActiveSession

from .models import Activity
from .serializers import ActivitySerializer

logger = logging.getLogger(__name__)


def _personalize(message: str, user) -> str:
    """
    Replace the actor's name / phone number at the start of an activity
    message with the second-person 'You'.

    e.g.  "Alice Wanjiru contributed KES 500 to Chama Pool"
          → "You contributed KES 500 to Chama Pool"
    """
    display = (getattr(user, 'name', '') or '').strip() or user.phone_number
    for prefix in ([display, user.phone_number] if display != user.phone_number else [user.phone_number]):
        if message.startswith(prefix):
            return 'You' + message[len(prefix):]
    return message


class ActivityFeedView(APIView):
    """
    GET /api/activity/
    Query params:
      type   — substring filter on activity_type (e.g. ?type=contribution)
      limit  — max records, default 50, max 200
      offset — pagination offset
    """
    permission_classes = [IsActiveSession]

    def get(self, request):
        activity_type = request.query_params.get('type')
        try:
            limit  = min(int(request.query_params.get('limit',  50)), 200)
            offset = int(request.query_params.get('offset', 0))
        except (ValueError, TypeError):
            return Response(
                {"error": "limit and offset must be integers."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        qs = Activity.objects.filter(user=request.user).order_by('-created_at')

        if activity_type:
            # icontains so "contribution" matches contribution_payment,
            # contribution_created, etc.
            qs = qs.filter(activity_type__icontains=activity_type)

        total      = qs.count()
        activities = list(qs[offset: offset + limit])

        # Personalize: every record belongs to request.user, so the actor is
        # always "you". Replace their name/phone at the start of the message.
        user = request.user
        for a in activities:
            a.message = _personalize(a.message, user)

        logger.info(
            "ActivityFeedView: user %s fetched activity feed (type=%s limit=%d offset=%d total=%d)",
            request.user.id, activity_type or '*', limit, offset, total,
        )

        serializer = ActivitySerializer(activities, many=True)
        return Response({
            'count':    total,
            'results':  serializer.data,
            'has_more': (offset + limit) < total,
        })
