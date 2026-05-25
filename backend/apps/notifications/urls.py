from django.urls import path

from .views import (
    NotificationListView,
    UnreadCountView,
    MarkReadView,
    MarkAllReadView,
    DeleteNotificationView,
    DeleteAllNotificationsView,
)

urlpatterns = [
    path('', NotificationListView.as_view()),
    path('unread-count/', UnreadCountView.as_view()),
    path('<int:notification_id>/read/', MarkReadView.as_view()),
    path('read-all/', MarkAllReadView.as_view()),
    path('<int:notification_id>/delete/', DeleteNotificationView.as_view()),
    path('delete-all/', DeleteAllNotificationsView.as_view()),
]
