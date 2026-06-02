import logging

from django.shortcuts import get_object_or_404

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from apps.users.auth import IsActiveSession

from .models import Reminder
from .serializers import ReminderSerializer, ReminderCreateSerializer, ReminderUpdateSerializer

logger = logging.getLogger(__name__)


class ReminderListCreateView(APIView):
    """
    GET  /api/reminders/        — list the authenticated user's reminders
    POST /api/reminders/        — create a new reminder
    """
    permission_classes = [IsActiveSession]

    def get(self, request):
        active_only = request.query_params.get('active', 'true').lower() == 'true'
        qs = Reminder.objects.filter(user=request.user)
        if active_only:
            qs = qs.filter(is_active=True)
        serializer = ReminderSerializer(qs, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = ReminderCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        reminder = serializer.save(user=request.user)
        logger.info(
            "ReminderListCreateView: user %s created reminder %s",
            request.user.id, reminder.id,
        )
        return Response(ReminderSerializer(reminder).data, status=status.HTTP_201_CREATED)


class ReminderDetailView(APIView):
    """
    GET    /api/reminders/<id>/  — retrieve
    PATCH  /api/reminders/<id>/  — update (reschedule, toggle active, edit text)
    DELETE /api/reminders/<id>/  — delete
    """
    permission_classes = [IsActiveSession]

    def _get_reminder(self, reminder_id, user):
        # Scoped to user — prevents IDOR access to other users' reminders
        return get_object_or_404(Reminder, id=reminder_id, user=user)

    def get(self, request, reminder_id):
        reminder = self._get_reminder(reminder_id, request.user)
        return Response(ReminderSerializer(reminder).data)

    def patch(self, request, reminder_id):
        reminder = self._get_reminder(reminder_id, request.user)
        serializer = ReminderUpdateSerializer(reminder, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        logger.info(
            "ReminderDetailView: user %s updated reminder %s",
            request.user.id, reminder_id,
        )
        return Response(ReminderSerializer(reminder).data)

    def delete(self, request, reminder_id):
        reminder = self._get_reminder(reminder_id, request.user)
        reminder.delete()
        logger.info(
            "ReminderDetailView: user %s deleted reminder %s",
            request.user.id, reminder_id,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class UpcomingRemindersView(APIView):
    """
    GET /api/reminders/upcoming/
    Returns the next N due reminders (active, sorted by next_fire_at).
    Used by the profile screen preview widget.
    """
    permission_classes = [IsActiveSession]

    def get(self, request):
        try:
            limit = min(int(request.query_params.get('limit', 5)), 20)
        except (ValueError, TypeError):
            return Response(
                {"error": "limit must be an integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        reminders = Reminder.objects.filter(
            user=request.user,
            is_active=True,
        ).order_by('next_fire_at')[:limit]
        return Response(ReminderSerializer(reminders, many=True).data)
