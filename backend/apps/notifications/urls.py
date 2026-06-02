from django.urls import path

from .views import (
    NotificationListView,
    UnreadCountView,
    MarkReadView,
    MarkAllReadView,
    DeleteNotificationView,
    DeleteAllNotificationsView,
    DeviceRegisterView,
    NotificationPreferencesView,
)

urlpatterns = [
    path('', NotificationListView.as_view()),
    path('unread-count/', UnreadCountView.as_view()),
    path('<int:notification_id>/read/', MarkReadView.as_view()),
    path('read-all/', MarkAllReadView.as_view()),
    path('<int:notification_id>/delete/', DeleteNotificationView.as_view()),
    path('delete-all/', DeleteAllNotificationsView.as_view()),
    # FCM device token registration
    path('devices/', DeviceRegisterView.as_view()),
    # User notification preferences
    path('preferences/', NotificationPreferencesView.as_view()),
]
