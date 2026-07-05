from django.urls import path

from .views import OpsMeView, OpsPingView

# Mounted at /api/ops/
urlpatterns = [
    path("me/", OpsMeView.as_view()),
    path("ping/", OpsPingView.as_view()),
]
