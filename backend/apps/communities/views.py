from django.db.models import Count, Max, Q
from django.db.models.functions import Coalesce, Greatest
from django.shortcuts import get_object_or_404

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from .models import Community, CommunityMembership, CommunityJoinRequest
from .serializers import CommunitySerializer, CommunityMembershipSerializer, CommunityJoinRequestSerializer
from .services import CommunityService


class MyCommunitiesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        communities = (
            Community.objects
            .filter(memberships__user=request.user, memberships__is_active=True)
            .distinct()
            .annotate(
                last_msg=Max('conversations__messages__created_at'),
                last_join=Max('memberships__joined_at'),
                last_request=Max('join_requests__created_at'),
                last_contrib=Max('contributions__created_at'),
            )
            .annotate(
                last_activity=Greatest(
                    Coalesce('last_msg', 'created_at'),
                    Coalesce('last_join', 'created_at'),
                    Coalesce('last_request', 'created_at'),
                    Coalesce('last_contrib', 'created_at'),
                    'created_at',
                )
            )
            .order_by('-last_activity')
        )
        return Response(CommunitySerializer(communities, many=True).data)


class DiscoverCommunitiesView(APIView):
    """
    GET /api/communities/discover/
    Query params:
      q        — name / description search (case-insensitive)
      category — filter by category slug  (e.g. savings, chama, welfare …)
      location — partial location filter
      limit    — max results, default 30, max 100
      offset   — pagination offset
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        q        = request.query_params.get('q', '').strip()
        category = request.query_params.get('category', '').strip()
        location = request.query_params.get('location', '').strip()
        limit    = min(int(request.query_params.get('limit',  30)), 100)
        offset   = int(request.query_params.get('offset', 0))

        # Only public communities the current user is NOT already a member of
        qs = (
            Community.objects
            .filter(is_private=False)
            .exclude(memberships__user=request.user, memberships__is_active=True)
            .annotate(
                annotated_member_count=Count(
                    'memberships',
                    filter=Q(memberships__is_active=True),
                    distinct=True,
                )
            )
        )

        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))
        if category:
            qs = qs.filter(category=category)
        if location:
            qs = qs.filter(location__icontains=location)

        qs = qs.order_by('-annotated_member_count', '-created_at')

        total       = qs.count()
        communities = list(qs[offset: offset + limit])

        return Response({
            'count':    total,
            'has_more': (offset + limit) < total,
            'results':  CommunitySerializer(
                communities, many=True, context={'request': request}
            ).data,
        })


class CommunityCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        share_price = request.data.get('share_price')
        serializer = CommunitySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        community = CommunityService.create_community(
            request.user, serializer.validated_data, share_price=share_price
        )
        return Response(CommunitySerializer(community).data, status=status.HTTP_201_CREATED)


class CommunityDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, community_id):
        community = get_object_or_404(Community, id=community_id)
        return Response(CommunitySerializer(community).data)


class JoinCommunityView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, community_id):
        community = get_object_or_404(Community, id=community_id)
        membership = CommunityService.join_community(request.user, community)
        return Response({"message": f"You joined {community.name}", "role": membership.role})


class LeaveCommunityView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, community_id):
        community = get_object_or_404(Community, id=community_id)
        CommunityService.leave_community(request.user, community)
        return Response({"message": f"You left {community.name}"})


class CommunityMembersView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, community_id):
        community = get_object_or_404(Community, id=community_id)
        members = CommunityService.get_members(community)
        return Response(CommunityMembershipSerializer(members, many=True).data)


class CommunityUpdateView(APIView):
    """PATCH /communities/<community_id>/update/ — creator or admin can amend community details."""
    permission_classes = [IsAuthenticated]

    ALLOWED_FIELDS = {'name', 'description', 'is_private', 'category', 'location'}

    def patch(self, request, community_id):
        community = get_object_or_404(Community, id=community_id)

        # Only creator or admin membership
        is_creator = community.created_by == request.user
        is_admin   = CommunityMembership.objects.filter(
            community=community, user=request.user,
            role__in=['admin', 'treasurer'], is_active=True,
        ).exists()

        if not is_creator and not is_admin:
            return Response(
                {"error": "Only the community creator or an admin can edit community details."},
                status=status.HTTP_403_FORBIDDEN,
            )

        payload = {k: v for k, v in request.data.items() if k in self.ALLOWED_FIELDS}
        if not payload:
            return Response(
                {"error": f"No valid fields provided. Editable fields: {sorted(self.ALLOWED_FIELDS)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = CommunitySerializer(community, data=payload, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        serializer.save()
        return Response(CommunitySerializer(community).data)


class CommunityDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, community_id):
        community = get_object_or_404(Community, id=community_id)
        if community.created_by != request.user:
            return Response({"error": "Only the creator can delete this community."}, status=403)
        community.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Role assignment
# ---------------------------------------------------------------------------

class AssignRoleView(APIView):
    """POST /communities/<community_id>/members/<membership_id>/role/"""
    permission_classes = [IsAuthenticated]

    def post(self, request, community_id, membership_id):
        community = get_object_or_404(Community, id=community_id)
        role = request.data.get("role")
        try:
            membership = CommunityService.assign_role(request.user, community, membership_id, role)
        except CommunityMembership.DoesNotExist:
            return Response({"error": "Member not found."}, status=404)
        return Response(CommunityMembershipSerializer(membership).data)


class RemoveMemberView(APIView):
    """DELETE /communities/<community_id>/members/<membership_id>/"""
    permission_classes = [IsAuthenticated]

    def delete(self, request, community_id, membership_id):
        community = get_object_or_404(Community, id=community_id)
        try:
            CommunityService.remove_member(request.user, community, membership_id)
        except CommunityMembership.DoesNotExist:
            return Response({"error": "Member not found."}, status=404)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Invite code lookup
# ---------------------------------------------------------------------------

class CommunityByInviteView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, code):
        community = CommunityService.get_community_by_invite(code)
        if not community:
            return Response({"error": "Invalid invite code."}, status=404)
        return Response(CommunitySerializer(community).data)


# ---------------------------------------------------------------------------
# Join requests
# ---------------------------------------------------------------------------

class JoinRequestCreateView(APIView):
    """POST /communities/invite/<code>/request/ — submit a join request."""
    permission_classes = [IsAuthenticated]

    def post(self, request, code):
        community = CommunityService.get_community_by_invite(code)
        if not community:
            return Response({"error": "Invalid invite code."}, status=404)
        req, _ = CommunityService.request_to_join(request.user, community)
        return Response(CommunityJoinRequestSerializer(req).data, status=201)


class JoinRequestActionView(APIView):
    """POST /communities/join-requests/<req_id>/action/ — admin approves/rejects."""
    permission_classes = [IsAuthenticated]

    def post(self, request, req_id):
        action = request.data.get("action")
        if action not in ("approve", "reject"):
            return Response({"error": "action must be 'approve' or 'reject'."}, status=400)
        try:
            req = CommunityService.action_join_request(request.user, req_id, action)
        except CommunityJoinRequest.DoesNotExist:
            return Response({"error": "Join request not found."}, status=404)
        return Response(CommunityJoinRequestSerializer(req).data)
