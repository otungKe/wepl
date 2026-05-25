from django.urls import path
from .views import ReminderListCreateView, ReminderDetailView, UpcomingRemindersView

urlpatterns = [
    path('',                        ReminderListCreateView.as_view()),
    path('upcoming/',               UpcomingRemindersView.as_view()),
    path('<int:reminder_id>/',      ReminderDetailView.as_view()),
]
