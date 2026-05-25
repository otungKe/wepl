from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from .models import Notification
from .serializers import NotificationSerializer
from .services import NotificationService


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
