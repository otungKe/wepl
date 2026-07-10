from django.urls import path

from .views import (
    OpsMeView, OpsPingView, OpsSearchView,
    StaffLoginView, StaffChangePasswordView,
)
from .views_accounts import Account360View, AccountsSearchView
from .views_communities import (
    OpsCommunitiesListView, OpsCommunityDetailView, OpsCommunityLifecycleView,
)
from .views_approvals import ApprovalDecideView, ApprovalDetailView, ApprovalsListView
from .views_exports import (
    AuditExportView, MemberStatementExportView, TransactionsExportView,
)
from .views_finops import FinopsActionView, FinopsQueuesView, FinopsReverseRequestView
from .views_health import (
    HealthOverviewView, NoticeDismissView, NoticesView,
    OutboxListView, OutboxRequeueView,
)
from .views_platform import OpsAuditLogView, OpsMetricsView
from .views_stepup import StepUpView, TotpConfirmView, TotpSetupView
from .views_support import (
    SupportRequestDetailView, SupportRequestResolveView, SupportRequestsView,
)
from .views_transactions import Transaction360View, TransactionsListView
from .views_users import OpsUser360View, OpsUsersListView, OpsUserStatusView
from .views_verification import (
    EddCaseView, EddDecisionView, EddQueueView,
    VerificationAssignView, VerificationCaseView, VerificationDecisionView,
    VerificationNoteView, VerificationQueueView, VerificationStatsView,
)

# Mounted at /api/ops/
urlpatterns = [
    path("auth/login/", StaffLoginView.as_view()),
    path("auth/change-password/", StaffChangePasswordView.as_view()),
    path("auth/totp/setup/", TotpSetupView.as_view()),
    path("auth/totp/confirm/", TotpConfirmView.as_view()),
    path("auth/step-up/", StepUpView.as_view()),
    path("me/", OpsMeView.as_view()),
    path("metrics/", OpsMetricsView.as_view()),
    path("audit/", OpsAuditLogView.as_view()),
    path("communities/", OpsCommunitiesListView.as_view()),
    path("communities/<int:community_id>/", OpsCommunityDetailView.as_view()),
    path("communities/<int:community_id>/lifecycle/", OpsCommunityLifecycleView.as_view()),
    path("users/", OpsUsersListView.as_view()),
    path("users/<int:user_id>/", OpsUser360View.as_view()),
    path("users/<int:user_id>/status/", OpsUserStatusView.as_view()),
    path("support/requests/", SupportRequestsView.as_view()),
    path("support/requests/<int:request_id>/", SupportRequestDetailView.as_view()),
    path("support/requests/<int:request_id>/resolve/", SupportRequestResolveView.as_view()),
    path("transactions/", TransactionsListView.as_view()),
    path("transactions/<int:tx_id>/", Transaction360View.as_view()),
    path("accounts/", AccountsSearchView.as_view()),
    path("accounts/<int:account_id>/", Account360View.as_view()),
    path("exports/transactions/", TransactionsExportView.as_view()),
    path("exports/audit/", AuditExportView.as_view()),
    path("users/<int:user_id>/statement/", MemberStatementExportView.as_view()),
    path("finops/", FinopsQueuesView.as_view()),
    path("finops/transactions/<int:ft_id>/action/", FinopsActionView.as_view()),
    path("finops/transactions/<int:ft_id>/reverse-request/", FinopsReverseRequestView.as_view()),
    path("approvals/", ApprovalsListView.as_view()),
    path("approvals/<int:request_id>/", ApprovalDetailView.as_view()),
    path("approvals/<int:request_id>/decide/", ApprovalDecideView.as_view()),
    path("health/", HealthOverviewView.as_view()),
    path("health/outbox/", OutboxListView.as_view()),
    path("health/outbox/<int:event_id>/requeue/", OutboxRequeueView.as_view()),
    path("notices/", NoticesView.as_view()),
    path("notices/<int:notice_id>/dismiss/", NoticeDismissView.as_view()),
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
