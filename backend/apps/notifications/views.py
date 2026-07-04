from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from .models import Notification, NotificationPreferences
from .serializers import NotificationSerializer
from .services import NotificationService

# Writable boolean flags via PATCH. 'security' is intentionally excluded —
# security & sign-in alerts are mandatory (returned read-only, never disableable).
PREF_FIELDS = ('push_enabled', 'payments', 'contributions', 'reminders',
               'communities', 'advances', 'quiet_hours_enabled')
READ_PREF_FIELDS = ('push_enabled', 'payments', 'contributions', 'reminders',
                    'communities', 'advances', 'security', 'quiet_hours_enabled')
QUIET_TIME_FIELDS = ('quiet_start', 'quiet_end')


def _serialize_prefs(prefs):
    data = {f: getattr(prefs, f) for f in READ_PREF_FIELDS}
    data['quiet_start'] = prefs.quiet_start.strftime('%H:%M')
    data['quiet_end']   = prefs.quiet_end.strftime('%H:%M')
    return data

VALID_PLATFORMS = {'android', 'ios'}


# =====================================
# LIST NOTIFICATIONS
# =====================================
class NotificationListView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):
        notifications = NotificationService.get_for_user(request.user)
        serializer = NotificationSerializer(notifications, many=True)
        return Response(serializer.data)


# =====================================
# UNREAD COUNT
# =====================================
class UnreadCountView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):
        count = NotificationService.unread_count(request.user)
        return Response({'unread_count': count})


# =====================================
# MARK ONE AS READ
# =====================================
class MarkReadView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, notification_id):
        NotificationService.mark_read(notification_id, request.user)
        return Response({'status': 'ok'})


# =====================================
# MARK ALL AS READ
# =====================================
class MarkAllReadView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):
        NotificationService.mark_all_read(request.user)
        return Response({'status': 'ok'})


# =====================================
# DELETE ONE
# =====================================
class DeleteNotificationView(APIView):

    permission_classes = [IsAuthenticated]

    def delete(self, request, notification_id):
        NotificationService.delete_one(notification_id, request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


# =====================================
# DELETE ALL
# =====================================
class DeleteAllNotificationsView(APIView):

    permission_classes = [IsAuthenticated]

    def delete(self, request):
        NotificationService.delete_all(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


# =====================================
# DEVICE TOKEN REGISTRATION (FCM)
# =====================================
class DeviceRegisterView(APIView):
    """
    POST  /notifications/devices/   — register or refresh an FCM token
    DELETE /notifications/devices/  — unregister on logout (body: {fcm_token})

    The mobile client calls POST on every app launch so the server always has a
    fresh token. Stale tokens are pruned automatically by the FCM task after a
    UNREGISTERED response from Firebase (Issue 19).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        fcm_token = request.data.get('fcm_token', '').strip()
        platform  = request.data.get('platform', 'android').lower()

        if not fcm_token:
            return Response({'error': 'fcm_token is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if platform not in VALID_PLATFORMS:
            return Response(
                {'error': f"platform must be one of: {', '.join(sorted(VALID_PLATFORMS))}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        NotificationService.register_device(request.user, fcm_token, platform)
        return Response({'status': 'registered'}, status=status.HTTP_200_OK)

    def delete(self, request):
        fcm_token = request.data.get('fcm_token', '').strip()
        if not fcm_token:
            return Response({'error': 'fcm_token is required.'}, status=status.HTTP_400_BAD_REQUEST)
        NotificationService.unregister_device(request.user, fcm_token)
        return Response(status=status.HTTP_204_NO_CONTENT)


class NotificationPreferencesView(APIView):
    """
    GET  /notifications/preferences/  — return the user's current preferences
    PATCH /notifications/preferences/ — update one or more preference flags

    All flags default to True on first access (auto-created row).
    Accepted fields: push_enabled, payments, contributions, reminders,
                     communities, advances.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        prefs, _ = NotificationPreferences.objects.get_or_create(user=request.user)
        return Response(_serialize_prefs(prefs))

    def patch(self, request):
        from datetime import datetime
        prefs, _ = NotificationPreferences.objects.get_or_create(user=request.user)
        changed = False

        for field in PREF_FIELDS:
            if field in request.data:
                val = request.data[field]
                if not isinstance(val, bool):
                    return Response({'error': f"'{field}' must be a boolean."},
                                    status=status.HTTP_400_BAD_REQUEST)
                setattr(prefs, field, val)
                changed = True

        for field in QUIET_TIME_FIELDS:
            if field in request.data:
                try:
                    setattr(prefs, field, datetime.strptime(str(request.data[field]), '%H:%M').time())
                except (ValueError, TypeError):
                    return Response({'error': f"'{field}' must be a time like '22:00'."},
                                    status=status.HTTP_400_BAD_REQUEST)
                changed = True

        if changed:
            prefs.save()
        return Response(_serialize_prefs(prefs))
