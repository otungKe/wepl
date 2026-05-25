from django.urls import path

from .views import (
    MyCommunitiesView,
    DiscoverCommunitiesView,
    CommunityCreateView,
    CommunityDetailView,
    CommunityUpdateView,
    JoinCommunityView,
    LeaveCommunityView,
    CommunityMembersView,
    CommunityDeleteView,
    AssignRoleView,
    RemoveMemberView,
    CommunityByInviteView,
    JoinRequestCreateView,
    JoinRequestActionView,
)

urlpatterns = [
    path('', MyCommunitiesView.as_view()),
    path('discover/', DiscoverCommunitiesView.as_view()),
    path('create/', CommunityCreateView.as_view()),
    path('<int:community_id>/', CommunityDetailView.as_view()),
    path('<int:community_id>/update/', CommunityUpdateView.as_view()),
    path('<int:community_id>/join/', JoinCommunityView.as_view()),
    path('<int:community_id>/leave/', LeaveCommunityView.as_view()),
    path('<int:community_id>/members/', CommunityMembersView.as_view()),
    path('<int:community_id>/members/<int:membership_id>/role/', AssignRoleView.as_view()),
    path('<int:community_id>/members/<int:membership_id>/', RemoveMemberView.as_view()),
    path('<int:community_id>/delete/', CommunityDeleteView.as_view()),
    # Invite code
    path('invite/<str:code>/', CommunityByInviteView.as_view()),
    path('invite/<str:code>/request/', JoinRequestCreateView.as_view()),
    # Admin actions
    path('join-requests/<int:req_id>/action/', JoinRequestActionView.as_view()),
]
