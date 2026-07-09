"""Communities ops module (/api/ops/communities/) — the console workspace the
lifecycle work promised: registry, community file, and the ops-only
suspend/unsuspend lever (moved here from the Django-admin stopgap).

Every mutation routes through CommunityService (the module's single door) and
writes both the community audit trail and the ops AuditEvent via record_action.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework import status as http
from rest_framework.response import Response

from apps.communities.models import Community

from .audit import record_action
from .permissions import RequireCapability, RequireStepUp
from .views import OpsAPIView


def _row(c):
    return {
        "id": c.id,
        "name": c.name,
        "category": c.category,
        "status": c.status,
        "is_private": c.is_private,
        "member_count": getattr(c, "member_count", None),
        "owner_phone": c.created_by.phone_number,
        "tenant": c.tenant.slug if c.tenant_id else None,
        "created_at": c.created_at.isoformat(),
    }


class OpsCommunitiesListView(OpsAPIView):
    """GET /api/ops/communities/?q=&status=&limit=&offset= — the registry."""
    permission_classes = [RequireCapability("communities.view")]

    def get(self, request):
        p = request.query_params
        qs = (Community.objects.select_related("created_by", "tenant")
              .annotate(member_count=Count(
                  "memberships", filter=Q(memberships__is_active=True), distinct=True)))
        if p.get("status") and p["status"] != "all":
            qs = qs.filter(status=p["status"])
        if p.get("q"):
            q = p["q"].strip()
            qs = qs.filter(Q(name__icontains=q) | Q(invite_code__iexact=q)
                           | (Q(pk=q) if q.isdigit() else Q()))
        qs = qs.order_by("-created_at")

        try:
            limit = min(max(int(p.get("limit", 50)), 1), 100)
            offset = max(int(p.get("offset", 0)), 0)
        except (TypeError, ValueError):
            limit, offset = 50, 0
        total = qs.count()
        return Response({
            "results": [_row(c) for c in qs[offset:offset + limit]],
            "count": total, "has_more": offset + limit < total,
        })


class OpsCommunityDetailView(OpsAPIView):
    """GET /api/ops/communities/<id>/ — the community file: profile, governance
    settings, membership stats, financial footprint, and its audit trail."""
    permission_classes = [RequireCapability("communities.view")]

    def get(self, request, community_id):
        from apps.audit.models import AuditEvent
        from apps.communities.services import CommunityService
        from apps.contributions.models import Contribution, SharesFund, WelfareFund

        c = get_object_or_404(
            Community.objects.select_related("created_by", "tenant"), id=community_id)
        memberships = c.memberships.filter(is_active=True)
        trail = [{
            "action": e.action, "actor": e.actor_label or "system",
            "metadata": e.metadata, "at": e.created_at.isoformat(),
        } for e in AuditEvent.objects.filter(
            target_type="community", target_id=str(c.id)).order_by("-created_at")[:25]]

        return Response({
            **_row(c),
            "description": c.description or "",
            "location": c.location,
            "owner_name": c.created_by.name or "",
            "members": {
                "active": memberships.count(),
                "admins": c.active_admin_count(),
                "treasurers": memberships.filter(role="treasurer").count(),
                "banned": c.memberships.filter(member_status="banned").count(),
                "max": c.max_members,
            },
            "settings": {
                "join_policy": c.join_policy,
                "invite_permission": c.invite_permission,
                "contribution_permission": c.contribution_permission,
                "member_list_visibility": c.member_list_visibility,
                "cooling_off_days": c.cooling_off_days,
            },
            "finance": {
                "contributions": Contribution.objects.filter(community=c).count(),
                "welfare_funds": WelfareFund.objects.filter(community=c).count(),
                "shares_funds": SharesFund.objects.filter(community=c).count(),
                "has_financial_history": CommunityService.has_financial_history(c),
            },
            "pending_join_requests": c.join_requests.filter(status="PENDING").count(),
            "audit_trail": trail,
        })


class OpsCommunityLifecycleView(OpsAPIView):
    """POST /api/ops/communities/<id>/lifecycle/ {action: suspend|unsuspend,
    reason} — the ops freeze lever (fraud investigation / compliance / court
    order). Suspension requires a reason; both directions are audited on the
    community trail AND the ops action log. Freezing a community touches its
    members' funds, so the lever requires a fresh step-up (OP-3)."""
    permission_classes = [RequireCapability("communities.manage"), RequireStepUp]

    def post(self, request, community_id):
        from apps.communities.services import CommunityService

        c = get_object_or_404(Community, id=community_id)
        action = (request.data.get("action") or "").strip()
        reason = (request.data.get("reason") or "").strip()

        try:
            if action == "suspend":
                if not reason:
                    return Response({"detail": "A reason is required to suspend."},
                                    status=http.HTTP_400_BAD_REQUEST)
                CommunityService.suspend_community(c, actor=None,
                                                   reason=f"ops:{request.user.email}: {reason}")
            elif action == "unsuspend":
                CommunityService.unsuspend_community(c, actor=None,
                                                     reason=f"ops:{request.user.email}: {reason}")
            else:
                return Response({"detail": f"Unknown action: {action!r}."},
                                status=http.HTTP_400_BAD_REQUEST)
        except ValidationError as exc:
            detail = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
            return Response({"detail": detail}, status=http.HTTP_409_CONFLICT)

        record_action(
            action=f"ops.community.{action}", actor=request.user, request=request,
            target_type="community", target_id=c.id, metadata={"reason": reason},
        )
        c.refresh_from_db()
        return Response({"id": c.id, "status": c.status})
