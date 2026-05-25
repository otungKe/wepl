from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import Activity
from .serializers import ActivitySerializer


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
    permission_classes = [IsAuthenticated]

    def get(self, request):
        activity_type = request.query_params.get('type')
        limit  = min(int(request.query_params.get('limit',  50)), 200)
        offset = int(request.query_params.get('offset', 0))

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

        serializer = ActivitySerializer(activities, many=True)
        return Response({
            'count':    total,
            'results':  serializer.data,
            'has_more': (offset + limit) < total,
        })