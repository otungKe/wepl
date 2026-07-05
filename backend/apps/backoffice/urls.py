from django.urls import path

from .views import (
    OpsMeView, OpsPingView, OpsSearchView,
    StaffLoginView, StaffChangePasswordView,
)
from .views_verification import (
    VerificationQueueView, VerificationCaseView, VerificationDecisionView,
)

# Mounted at /api/ops/
urlpatterns = [
    path("auth/login/", StaffLoginView.as_view()),
    path("auth/change-password/", StaffChangePasswordView.as_view()),
    path("me/", OpsMeView.as_view()),
    path("ping/", OpsPingView.as_view()),
    path("search/", OpsSearchView.as_view()),
    # Verification Centre (P1)
    path("verification/queue/", VerificationQueueView.as_view()),
    path("verification/<int:user_id>/", VerificationCaseView.as_view()),
    path("verification/<int:user_id>/decision/", VerificationDecisionView.as_view()),
]
