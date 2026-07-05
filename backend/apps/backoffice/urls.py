from django.urls import path

from .views import (
    OpsMeView, OpsPingView, OpsSearchView,
    StaffLoginView, StaffChangePasswordView,
)

# Mounted at /api/ops/
urlpatterns = [
    path("auth/login/", StaffLoginView.as_view()),
    path("auth/change-password/", StaffChangePasswordView.as_view()),
    path("me/", OpsMeView.as_view()),
    path("ping/", OpsPingView.as_view()),
    path("search/", OpsSearchView.as_view()),
]
