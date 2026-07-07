from django.urls import path

from .views import (
    OpsMeView, OpsPingView, OpsSearchView,
    StaffLoginView, StaffChangePasswordView,
)
from .views_communities import (
    OpsCommunitiesListView, OpsCommunityDetailView, OpsCommunityLifecycleView,
)
from .views_platform import OpsAuditLogView, OpsMetricsView
from .views_verification import (
    EddCaseView, EddDecisionView, EddQueueView,
    VerificationAssignView, VerificationCaseView, VerificationDecisionView,
    VerificationNoteView, VerificationQueueView, VerificationStatsView,
)

# Mounted at /api/ops/
urlpatterns = [
    path("auth/login/", StaffLoginView.as_view()),
    path("auth/change-password/", StaffChangePasswordView.as_view()),
    path("me/", OpsMeView.as_view()),
    path("metrics/", OpsMetricsView.as_view()),
    path("audit/", OpsAuditLogView.as_view()),
    path("communities/", OpsCommunitiesListView.as_view()),
    path("communities/<int:community_id>/", OpsCommunityDetailView.as_view()),
    path("communities/<int:community_id>/lifecycle/", OpsCommunityLifecycleView.as_view()),
    path("ping/", OpsPingView.as_view()),
    path("search/", OpsSearchView.as_view()),
    # Verification Centre (P1)
    path("verification/queue/", VerificationQueueView.as_view()),
    path("verification/stats/", VerificationStatsView.as_view()),
    path("verification/edd/", EddQueueView.as_view()),
    path("verification/edd/<uuid:case_id>/", EddCaseView.as_view()),
    path("verification/edd/<uuid:case_id>/decision/", EddDecisionView.as_view()),
    path("verification/<int:user_id>/", VerificationCaseView.as_view()),
    path("verification/<int:user_id>/decision/", VerificationDecisionView.as_view()),
    path("verification/<int:user_id>/notes/", VerificationNoteView.as_view()),
    path("verification/<int:user_id>/assign/", VerificationAssignView.as_view()),
]
