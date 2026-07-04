import logging

from django.db.models import Count, Max, Q
from django.db.models.functions import Coalesce, Greatest
from django.shortcuts import get_object_or_404

from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import AuditService
from apps.core.policy import can, require
from apps.users.auth import IsActiveSession

from .models import Community, CommunityJoinRequest, CommunityMembership
from .serializers import (
    CommunityJoinRequestSerializer,
    CommunityMembershipSerializer,
    CommunitySerializer,
    CommunityWriteSerializer,
)
from .services import CommunityService

logger = logging.getLogger(__name__)


def _ctx(request):
    """Serializer context carrying the current request (for is_member checks)."""
    return {"request": request}


def _enrich_communities(communities):
    """Attach real per-community highlight figures used by the web/mobile cards:

      • total_managed — pooled money held across the community's funds (each
        contribution pool + welfare + shares), read from the ledger balance
        projection in batch (not per-fund).
      • pending_count — items awaiting action: pending join requests +
        pending disbursement requests + pending welfare claims.

    Attached as plain attributes (mirrors annotated_member_count); only set on
    the caller's own communities, so the discover feed leaves them None. Runs a
    fixed handful of queries regardless of how many communities are passed.
    """
    from collections import defaultdict
    from decimal import Decimal
    from apps.contributions.models import (
        Contribution, WelfareFund, SharesFund, DisbursementRequest, WelfareClaim,
    )
    from apps.ledger.balances import fund_balances

    ids = [c.id for c in communities]
    if not ids:
        return communities

    # ── total_managed: sum ledger balances of every fund owned by the community
    contribs = list(Contribution.objects.filter(community_id__in=ids)
                    .values_list("id", "community_id"))
    welfares = list(WelfareFund.objects.filter(community_id__in=ids)
                    .values_list("id", "community_id"))
    shares   = list(SharesFund.objects.filter(community_id__in=ids)
                    .values_list("id", "community_id"))

    contrib_bal = fund_balances("contribution", [f for f, _ in contribs])
    welfare_bal = fund_balances("welfare",      [f for f, _ in welfares])
    shares_bal  = fund_balances("shares",       [f for f, _ in shares])

    totals = defaultdict(lambda: Decimal("0"))
    for fund_id, cid in contribs:
        totals[cid] += contrib_bal.get(fund_id, Decimal("0"))
    for fund_id, cid in welfares:
        totals[cid] += welfare_bal.get(fund_id, Decimal("0"))
    for fund_id, cid in shares:
        totals[cid] += shares_bal.get(fund_id, Decimal("0"))

    # ── pending_count: join requests + disbursement requests + welfare claims
    pending = defaultdict(int)
    for cid, n in (CommunityJoinRequest.objects
                   .filter(community_id__in=ids, status="PENDING")
                   .values_list("community_id").annotate(c=Count("id"))):
        pending[cid] += n
    for cid, n in (DisbursementRequest.objects
                   .filter(contribution__community_id__in=ids, status="PENDING")
                   .values_list("contribution__community_id").annotate(c=Count("id"))):
        pending[cid] += n
    for cid, n in (WelfareClaim.objects
                   .filter(fund__community_id__in=ids, status="PENDING")
                   .values_list("fund__community_id").annotate(c=Count("id"))):
        pending[cid] += n

    for c in communities:
        c.total_managed = totals.get(c.id, Decimal("0"))
        c.pending_count = pending.get(c.id, 0)
    return communities


# ── My communities ─────────────────────────────────────────────────────────────

class MyCommunitiesView(APIView):
    permission_classes = [IsActiveSession]

    def get(self, request):
        communities = (
            Community.objects
            .filter(memberships__user=request.user, memberships__is_active=True)
            .distinct()
            .annotate(
                last_msg=Max("conversations__messages__created_at"),
                last_join=Max("memberships__joined_at"),
                last_request=Max("join_requests__created_at"),
                last_contrib=Max("contributions__created_at"),
            )
            .annotate(
                last_activity=Greatest(
                    Coalesce("last_msg",     "created_at"),
                    Coalesce("last_join",    "created_at"),
                    Coalesce("last_request", "created_at"),
                    Coalesce("last_contrib", "created_at"),
                    "created_at",
                )
            )
            .order_by("-last_activity")
        )
        communities = _enrich_communities(list(communities))
        return Response(CommunitySerializer(communities, many=True, context=_ctx(request)).data)


# ── Discover ───────────────────────────────────────────────────────────────────

class DiscoverCommunitiesView(APIView):
    """
    GET /api/communities/discover/
    Query params:
      q        — name / description search (case-insensitive)
      category — filter by category slug
      location — partial match
      limit    — max results per page (default 30, max 100)
      offset   — pagination offset
    """
    permission_classes = [IsActiveSession]

    def get(self, request):
        q        = request.query_params.get("q", "").strip()
        category = request.query_params.get("category", "").strip()
        location = request.query_params.get("location", "").strip()

        try:
            limit  = min(max(int(request.query_params.get("limit",  30)), 1), 100)
            offset = max(int(request.query_params.get("offset",  0)), 0)
        except (TypeError, ValueError):
            raise ValidationError("limit and offset must be integers.")

        qs = (
            Community.objects
            .filter(is_private=False)
            .exclude(memberships__user=request.user, memberships__is_active=True)
            .annotate(
                annotated_member_count=Count(
                    "memberships", filter=Q(memberships__is_active=True), distinct=True,
                )
            )
        )
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))
        if category:
            qs = qs.filter(category=category)
        if location:
            qs = qs.filter(location__icontains=location)

        qs    = qs.order_by("-annotated_member_count", "-created_at")
        total = qs.count()

        return Response({
            "count":    total,
            "has_more": (offset + limit) < total,
            "results":  CommunitySerializer(
                list(qs[offset: offset + limit]), many=True, context=_ctx(request),
            ).data,
        })


# ── CRUD ───────────────────────────────────────────────────────────────────────

class CommunityCreateView(APIView):
    permission_classes = [IsActiveSession]

    def post(self, request):
        share_price = request.data.get("share_price")
        serializer  = CommunityWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        community = CommunityService.create_community(
            request.user, serializer.validated_data, share_price=share_price,
        )
        return Response(
            CommunitySerializer(community, context=_ctx(request)).data,
            status=status.HTTP_201_CREATED,
        )


class CommunityDetailView(APIView):
    permission_classes = [IsActiveSession]

    def get(self, request, community_id):
        community = get_object_or_404(Community, id=community_id)
        # Cross-tenant guardrail (P6-05): refuse + audit access to another
        # tenant's community when the request is pinned to a tenant.
        from apps.tenants.guards import guard_tenant
        guard_tenant(community.tenant_id, request=request,
                     resource_type='community', resource_id=community.id)
        # Private communities are only visible to active members.
        if community.is_private and not CommunityService.is_member(request.user, community):
            raise PermissionDenied("This community is private.")
        return Response(CommunitySerializer(community, context=_ctx(request)).data)


class CommunityUpdateView(APIView):
    """PATCH — creator or admin can amend community details including governance settings."""
    permission_classes = [IsActiveSession]
    ALLOWED_FIELDS = {
        "name", "description", "is_private", "category", "location",
        # Section A governance settings
        "join_policy", "invite_permission", "contribution_permission",
        "member_list_visibility", "max_members",
        # Section B
        "cooling_off_days",
    }

    def patch(self, request, community_id):
        community = get_object_or_404(Community, id=community_id)
        require(request.user, "community.update", community,
                "Only the creator or an admin can edit community details.")

        payload = {k: v for k, v in request.data.items() if k in self.ALLOWED_FIELDS}
        if not payload:
            raise ValidationError(
                f"No valid fields provided. Editable: {sorted(self.ALLOWED_FIELDS)}"
            )

        # Guard: can't reduce max_members below current active member count
        if "max_members" in payload and payload["max_members"] is not None:
            active = community.memberships.filter(is_active=True).count()
            if int(payload["max_members"]) < active:
                raise ValidationError(
                    f"max_members ({payload['max_members']}) cannot be less than "
                    f"the current active member count ({active})."
                )

        serializer = CommunityWriteSerializer(community, data=payload, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        logger.info("Community '%s' (id=%s) updated by %s", community.name, community.id, request.user.phone_number)
        AuditService.log(
            "community.settings_updated", actor=request.user, target=community,
            tenant=community.tenant_id, request=request,
            metadata={"fields": sorted(payload.keys())},
        )
        return Response(CommunitySerializer(community, context=_ctx(request)).data)


class CommunityDeleteView(APIView):
    permission_classes = [IsActiveSession]

    def delete(self, request, community_id):
        community = get_object_or_404(Community, id=community_id)
        require(request.user, "community.delete", community,
                "Only the creator can delete this community.")
        logger.info("Community '%s' (id=%s) deleted by %s", community.name, community.id, request.user.phone_number)
        # Capture identity before the row is gone.
        AuditService.log(
            "community.deleted", actor=request.user, target_type="community",
            target_id=str(community.id), tenant=community.tenant_id, request=request,
            metadata={"name": community.name},
        )
        community.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── Membership ─────────────────────────────────────────────────────────────────

class JoinCommunityView(APIView):
    """
    Direct join endpoint.

    Enforces join_policy:
      open        → join immediately (if below max_members)
      request     → redirect to the request-to-join flow
      invite_only → blocked; must use invite link
    """
    permission_classes = [IsActiveSession]

    def post(self, request, community_id):
        community = get_object_or_404(Community, id=community_id)

        policy = community.join_policy

        if policy == Community.JoinPolicy.INVITE_ONLY:
            raise PermissionDenied(
                "This community is invite-only. Ask a member for an invite link."
            )

        if policy == Community.JoinPolicy.REQUEST:
            # Redirect the caller to submit a join request instead.
            return Response(
                {
                    "error": "join_request_required",
                    "message": "This community requires admin approval to join. "
                               "Submit a join request via the invite code flow.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # policy == OPEN — check member cap before joining
        if community.max_members:
            active = community.memberships.filter(is_active=True).count()
            if active >= community.max_members:
                raise ValidationError(
                    f"This community has reached its maximum of {community.max_members} members."
                )

        membership = CommunityService.join_community(request.user, community)
        return Response({"message": f"You joined {community.name}", "role": membership.role})


class LeaveCommunityView(APIView):
    permission_classes = [IsActiveSession]

    def post(self, request, community_id):
        community = get_object_or_404(Community, id=community_id)
        CommunityService.leave_community(request.user, community)
        return Response({"message": f"You left {community.name}"})


class CommunityMuteView(APIView):
    """POST /communities/<id>/mute/ {muted: bool} — mute/unmute this community's
    push notifications for the requesting member (in-app activity still shows)."""
    permission_classes = [IsActiveSession]

    def post(self, request, community_id):
        muted = bool(request.data.get('muted', True))
        m = CommunityMembership.objects.filter(
            community_id=community_id, user=request.user, is_active=True,
        ).first()
        if not m:
            return Response({"error": "You are not a member of this community."},
                            status=status.HTTP_404_NOT_FOUND)
        m.notifications_muted = muted
        m.save(update_fields=['notifications_muted'])
        return Response({"muted": m.notifications_muted})


class CommunityMembersView(APIView):
    """
    GET /communities/<id>/members/

    Respects member_list_visibility:
      all    → any active member can see the full list
      admins → only admins/creator can see the full list;
               regular members see only their own membership row
    """
    permission_classes = [IsActiveSession]

    def get(self, request, community_id):
        community = get_object_or_404(Community, id=community_id)

        # Must be a member (creator ranks above member) to see the roster at all.
        require(request.user, "community.view", community,
                "You are not a member of this community.")

        # Full roster visibility = the community allows ALL members to see it,
        # OR the actor has admin-level authority (policy decides the role part).
        show_all = (
            community.member_list_visibility == Community.MemberListVisibility.ALL
            or can(request.user, "community.members.view_all", community)
        )
        if not show_all:
            # Restricted list — caller sees only their own row.
            own = community.memberships.filter(user=request.user, is_active=True)
            return Response(CommunityMembershipSerializer(own, many=True).data)

        members = CommunityService.get_members(community)
        return Response(CommunityMembershipSerializer(members, many=True).data)


# ── Role management ────────────────────────────────────────────────────────────

class AssignRoleView(APIView):
    """POST /communities/<community_id>/members/<membership_id>/role/"""
    permission_classes = [IsActiveSession]

    def post(self, request, community_id, membership_id):
        community = get_object_or_404(Community, id=community_id)
        try:
            membership = CommunityService.assign_role(
                request.user, community, membership_id, request.data.get("role"),
            )
        except CommunityMembership.DoesNotExist:
            return Response({"error": "Member not found."}, status=404)
        return Response(CommunityMembershipSerializer(membership).data)


class RemoveMemberView(APIView):
    """DELETE /communities/<community_id>/members/<membership_id>/"""
    permission_classes = [IsActiveSession]

    def delete(self, request, community_id, membership_id):
        community = get_object_or_404(Community, id=community_id)
        try:
            CommunityService.remove_member(request.user, community, membership_id)
        except CommunityMembership.DoesNotExist:
            return Response({"error": "Member not found."}, status=404)
        return Response(status=status.HTTP_204_NO_CONTENT)


class TransferOwnershipView(APIView):
    """POST /communities/<community_id>/transfer-ownership/  body: {membership_id}

    Hand the community to another active member (ADR-0011)."""
    permission_classes = [IsActiveSession]

    def post(self, request, community_id):
        community = get_object_or_404(Community, id=community_id)
        membership_id = request.data.get("membership_id")
        if not membership_id:
            raise ValidationError("membership_id is required.")
        community = CommunityService.transfer_ownership(
            request.user, community, membership_id,
        )
        return Response(CommunitySerializer(community, context=_ctx(request)).data)


# ── Invite code ────────────────────────────────────────────────────────────────

class CommunityByInviteView(APIView):
    permission_classes = [IsActiveSession]

    def get(self, request, code):
        community = CommunityService.get_community_by_invite(code)
        if not community:
            return Response({"error": "Invalid invite code."}, status=404)
        return Response(CommunitySerializer(community, context=_ctx(request)).data)


# ── Join requests ──────────────────────────────────────────────────────────────

class JoinRequestCreateView(APIView):
    """POST /communities/invite/<code>/request/ — submit a join request."""
    permission_classes = [IsActiveSession]

    def post(self, request, code):
        community = CommunityService.get_community_by_invite(code)
        if not community:
            return Response({"error": "Invalid invite code."}, status=404)
        req, _ = CommunityService.request_to_join(request.user, community)
        return Response(CommunityJoinRequestSerializer(req).data, status=201)


class MyJoinRequestsView(APIView):
    """GET /communities/my-requests/ — list the current user's pending join requests."""
    permission_classes = [IsActiveSession]

    def get(self, request):
        requests = (
            CommunityJoinRequest.objects
            .filter(requester=request.user, status="PENDING")
            .select_related("community")
            .order_by("-created_at")
        )
        data = [
            {
                "id":          r.id,
                "community_id":    r.community.id,
                "community_name":  r.community.name,
                "community_photo": r.community.community_photo.url if r.community.community_photo else None,
                "member_count":    r.community.member_count if hasattr(r.community, 'member_count') else 0,
                "created_at":  r.created_at.isoformat(),
            }
            for r in requests
        ]
        return Response(data)


class JoinRequestCreateByIdView(APIView):
    """POST /communities/<id>/request/ — submit a join request by community ID.

    Used by the Discover flow where the serializer withholds invite_code from
    non-members, so the client must use the community ID instead.
    """
    permission_classes = [IsActiveSession]

    def post(self, request, community_id):
        community = get_object_or_404(Community, id=community_id)
        try:
            req, _ = CommunityService.request_to_join(request.user, community)
        except (ValidationError, Exception) as e:
            msg = e.detail[0] if hasattr(e, 'detail') else str(e)
            return Response({"error": msg}, status=400)
        return Response(CommunityJoinRequestSerializer(req).data, status=201)


class JoinRequestActionView(APIView):
    """POST /communities/join-requests/<req_id>/action/ — admin approves/rejects."""
    permission_classes = [IsActiveSession]

    def post(self, request, req_id):
        action = request.data.get("action")
        if action not in ("approve", "reject"):
            return Response({"error": "action must be 'approve' or 'reject'."}, status=400)
        try:
            req = CommunityService.action_join_request(request.user, req_id, action)
        except CommunityJoinRequest.DoesNotExist:
            return Response({"error": "Join request not found."}, status=404)
        return Response(CommunityJoinRequestSerializer(req).data)
