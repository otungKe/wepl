from django.urls import path

from .views import OpsMeView, OpsPingView, OpsSearchView

# Mounted at /api/ops/
urlpatterns = [
    path("me/", OpsMeView.as_view()),
    path("ping/", OpsPingView.as_view()),
    path("search/", OpsSearchView.as_view()),
]
