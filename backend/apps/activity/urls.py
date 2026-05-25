from django.urls import path
from .views import ActivityFeedView

urlpatterns = [
    path('', ActivityFeedView.as_view()),
]