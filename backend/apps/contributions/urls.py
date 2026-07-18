from django.urls import path

from .views import (
    ContributionCreateView, MyContributionsView, CommunityContributionsView,
    OpenContributionsView, DiscoverCampaignsView, ContributionDetailView, ContributionByInviteView,
    JoinContributionView, LeaveContributionView, ContributionParticipantsView,
    ContributeView, MyTransactionsView, ContributionTransactionsView,
    ContributionCloseView, ContributionReopenView, ContributionArchiveView,
    ContributionDeleteView, ContributionUpdateView,
    ROSCARotationView, ROSCAAdvanceSlotView,
    DisbursementRequestListCreateView, DisbursementVoteView, DisbursementCancelView,
    ExternalIncomeView, PoolExpenseRequestView, SurplusDistributionRequestView,
    PoolActionListView, PoolActionApproveView, PoolActionRejectView, PoolActionCancelView,
    CommunitySharesFundView, CommunitySharesContributeView,
    WelfareClaimVoteView,
    WelfareFundView, WelfareContributeView, WelfareClaimListCreateView, WelfareActivityView,
    AdvanceListCreateView, AdvanceActionView, MyAdvancesView,
    StandingOrderListCreateView, StandingOrderExecuteView, StandingOrderCancelView, StandingOrderUpdateView,
    AmendmentListCreateView, AmendmentVoteView, AmendmentWithdrawView,
    ContributionJoinRequestListView, ContributionJoinRequestActionView,
    ContributionInviteView, ContributionInviteRespondView,
    MyContributionJoinRequestView, MyContributionInviteView,
)

urlpatterns = [
    # Core
    path('',                                          MyContributionsView.as_view()),
    path('create/',                                   ContributionCreateView.as_view()),
    path('open/',                                     OpenContributionsView.as_view()),
    path('campaigns/',                                DiscoverCampaignsView.as_view()),
    path('community/<int:community_id>/',             CommunityContributionsView.as_view()),
    path('transactions/',                             MyTransactionsView.as_view()),
    path('invite/<str:invite_code>/',                 ContributionByInviteView.as_view()),
    path('contribute/',                               ContributeView.as_view()),

    path('<int:contribution_id>/',                    ContributionDetailView.as_view()),
    path('<int:contribution_id>/update/',             ContributionUpdateView.as_view()),
    path('<int:contribution_id>/join/',               JoinContributionView.as_view()),
    path('<int:contribution_id>/leave/',              LeaveContributionView.as_view()),
    path('<int:contribution_id>/close/',              ContributionCloseView.as_view()),
    path('<int:contribution_id>/reopen/',             ContributionReopenView.as_view()),
    path('<int:contribution_id>/archive/',            ContributionArchiveView.as_view()),
    path('<int:contribution_id>/delete/',             ContributionDeleteView.as_view()),
    path('<int:contribution_id>/participants/',       ContributionParticipantsView.as_view()),
    path('<int:contribution_id>/transactions/',       ContributionTransactionsView.as_view()),

    # ROSCA
    path('<int:contribution_id>/rosca/',              ROSCARotationView.as_view()),
    path('<int:contribution_id>/rosca/advance/',      ROSCAAdvanceSlotView.as_view()),

    # Collective-fund admin actions (ADR-0027) — maker-checked spend + distribution
    path('<int:contribution_id>/external-income/',    ExternalIncomeView.as_view()),
    path('<int:contribution_id>/pool-expense/',       PoolExpenseRequestView.as_view()),
    path('<int:contribution_id>/distribute/',         SurplusDistributionRequestView.as_view()),
    path('<int:contribution_id>/pool-actions/',       PoolActionListView.as_view()),
    path('pool-actions/<int:request_id>/approve/',    PoolActionApproveView.as_view()),
    path('pool-actions/<int:request_id>/reject/',     PoolActionRejectView.as_view()),
    path('pool-actions/<int:request_id>/cancel/',     PoolActionCancelView.as_view()),

    # Disbursement
    path('<int:contribution_id>/disbursements/',      DisbursementRequestListCreateView.as_view()),
    path('disbursements/<int:request_id>/vote/',      DisbursementVoteView.as_view()),
    path('disbursements/<int:request_id>/cancel/',    DisbursementCancelView.as_view()),

    # Shares fund (community-scoped)
    path('shares/<int:community_id>/',               CommunitySharesFundView.as_view()),
    path('shares/<int:community_id>/contribute/',    CommunitySharesContributeView.as_view()),

    # Welfare (community-scoped)
    path('welfare/claims/<int:claim_id>/vote/',       WelfareClaimVoteView.as_view()),
    path('welfare/<int:community_id>/',              WelfareFundView.as_view()),
    path('welfare/<int:community_id>/contribute/',   WelfareContributeView.as_view()),
    path('welfare/<int:community_id>/claims/',       WelfareClaimListCreateView.as_view()),
    path('welfare/<int:community_id>/activity/',     WelfareActivityView.as_view()),

    # Emergency advances
    path('<int:contribution_id>/advances/',           AdvanceListCreateView.as_view()),
    path('advances/<int:advance_id>/action/',         AdvanceActionView.as_view()),
    path('advances/mine/',                            MyAdvancesView.as_view()),

    # Standing Orders
    path('<int:contribution_id>/standing-orders/',    StandingOrderListCreateView.as_view()),
    path('standing-orders/<int:order_id>/execute/',   StandingOrderExecuteView.as_view()),
    path('standing-orders/<int:order_id>/cancel/',    StandingOrderCancelView.as_view()),
    path('standing-orders/<int:order_id>/update/',    StandingOrderUpdateView.as_view()),

    # Amendments
    path('<int:contribution_id>/amendments/',              AmendmentListCreateView.as_view()),
    path('amendments/<int:amendment_id>/vote/',            AmendmentVoteView.as_view()),
    path('amendments/<int:amendment_id>/withdraw/',        AmendmentWithdrawView.as_view()),

    # Join requests & invitations
    path('<int:contribution_id>/join-requests/',            ContributionJoinRequestListView.as_view()),
    path('join-requests/<int:request_id>/action/',          ContributionJoinRequestActionView.as_view()),
    path('<int:contribution_id>/invite/',                   ContributionInviteView.as_view()),
    path('invitations/<int:request_id>/respond/',           ContributionInviteRespondView.as_view()),
    path('<int:contribution_id>/my-join-request/',          MyContributionJoinRequestView.as_view()),
    path('<int:contribution_id>/my-invite/',                MyContributionInviteView.as_view()),
]
