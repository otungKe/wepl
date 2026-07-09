"""Users ops module (/api/ops/users/) — the member registry and the User 360.

Per the Operations Platform review: the 360 is a composed READ across the
owning domains (identity, verification, communities, ledger-derived finance,
sessions) — no stored aggregates; the only writes route through
UserService.deactivate_user / reactivate_user (the domain's single door).
The financial block is ledger-projection data only — Member Financial 360
semantics, no wallet concept.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status as http
from rest_framework.response import Response

from .audit import record_action
from .permissions import RequireCapability, RequireStepUp
from .views import OpsAPIView

User = get_user_model()


class OpsUsersListView(OpsAPIView):
    """GET /api/ops/users/?q=&state=&limit=&offset= — the member registry."""
    permission_classes = [RequireCapability("users.view")]

    def get(self, request):
        p = request.query_params
        qs = User.objects.filter(is_staff=False)
        state = p.get("state", "all")
        if state == "active":
            qs = qs.filter(is_active=True)
        elif state == "deactivated":
            qs = qs.filter(is_active=False)
        if p.get("q"):
            q = p["q"].strip()
            qs = qs.filter(Q(phone_number__icontains=q) | Q(name__icontains=q)
                           | (Q(pk=q) if q.isdigit() else Q()))
        qs = qs.order_by("-date_joined")

        try:
            limit = min(max(int(p.get("limit", 50)), 1), 100)
            offset = max(int(p.get("offset", 0)), 0)
        except (TypeError, ValueError):
            limit, offset = 50, 0
        total = qs.count()
        rows = [{
            "id": u.pk,
            "phone_number": u.phone_number,
            "name": u.name,
            "is_active": u.is_active,
            "phone_verified": u.is_phone_verified,
            "kyc_status": u.kyc_status,
            "tier": 1 if u.is_tier1 else 0,
            "joined": u.date_joined.isoformat(),
            "last_seen": u.last_seen.isoformat() if u.last_seen else None,
        } for u in qs[offset:offset + limit]]
        return Response({"results": rows, "count": total,
                         "has_more": offset + limit < total})


class OpsUser360View(OpsAPIView):
    """GET /api/ops/users/<id>/ — the User 360."""
    permission_classes = [RequireCapability("users.view")]

    def get(self, request, user_id):
        u = get_object_or_404(User, pk=user_id, is_staff=False)
        return Response({
            "identity": self._identity(u),
            "verification": self._verification(u),
            "communities": self._communities(u),
            "financial": self._financial(u),
            "sessions": self._sessions(u),
            "audit_trail": self._audit(u),
        })

    @staticmethod
    def _identity(u):
        return {
            "id": u.pk, "phone_number": u.phone_number, "name": u.name,
            "is_active": u.is_active, "phone_verified": u.is_phone_verified,
            "tier": 1 if u.is_tier1 else 0,
            "joined": u.date_joined.isoformat(),
            "last_seen": u.last_seen.isoformat() if u.last_seen else None,
        }

    @staticmethod
    def _verification(u):
        from apps.users.models import VerificationRequest
        out = {"kyc_status": u.kyc_status, "case": None, "open_requests": 0}
        kyc = getattr(u, "kyc", None) if u.kyc_status != "not_submitted" else None
        if kyc:
            case = kyc.cases.order_by("-opened_at").first()
            out.update({
                "email_verified": kyc.email_verified,
                "resubmission_requested": kyc.resubmission_requested or [],
                "case": {
                    "reference": f"VC-{case.id.hex[:8].upper()}",
                    "state": case.state,
                } if case else None,
            })
        out["open_requests"] = VerificationRequest.objects.filter(
            user=u).exclude(status="resolved").count()
        return out

    @staticmethod
    def _communities(u):
        from apps.communities.models import CommunityMembership
        return [{
            "id": m.community_id, "name": m.community.name,
            "role": m.role, "community_status": m.community.status,
            "joined": m.joined_at.isoformat(),
        } for m in (CommunityMembership.objects
                    .filter(user=u, is_active=True)
                    .select_related("community")[:25])]

    @staticmethod
    def _financial(u):
        """Member Financial 360 block: ledger-projection balances only —
        never stored counters (ADR-0002)."""
        from decimal import Decimal
        from apps.contributions.models import ContributionParticipant, EmergencyAdvance
        from apps.controls.models import ControlOverride, HeldMovement
        from apps.ledger.balances import account_balance
        from apps.ledger.coa import member_fund_account

        positions = []
        total = Decimal("0")
        parts = (ContributionParticipant.objects
                 .filter(user=u, is_active=True)
                 .select_related("contribution")[:20])
        for part in parts:
            acct = member_fund_account(user=u, fund_type="contribution",
                                       fund_id=part.contribution_id)
            bal = account_balance(acct)
            total += bal
            positions.append({"contribution_id": part.contribution_id,
                              "name": part.contribution.name,
                              "balance": str(bal)})
        from django.utils import timezone
        return {
            "positions": positions,
            "total_position": str(total),
            "open_advances": EmergencyAdvance.objects.filter(
                borrower=u, status__in=("PENDING", "APPROVED", "DISBURSED")).count(),
            "open_holds": HeldMovement.objects.filter(
                subject_user=u, status="OPEN").count(),
            "active_overrides": ControlOverride.objects.filter(
                user=u, consumed_at__isnull=True,
                expires_at__gt=timezone.now()).count(),
        }

    @staticmethod
    def _sessions(u):
        from apps.users.models import UserSession
        active = UserSession.objects.filter(user=u, revoked_at__isnull=True)
        latest = active.order_by("-last_seen_at").first()
        return {
            "active": active.count(),
            "latest_device": latest.device_label if latest else None,
            "latest_seen": latest.last_seen_at.isoformat() if latest else None,
        }

    @staticmethod
    def _audit(u):
        from apps.audit.models import AuditEvent
        qs = AuditEvent.objects.filter(
            Q(actor=u) | Q(target_type="user", target_id=str(u.pk))
        ).order_by("-created_at")[:15]
        return [{"action": e.action, "actor": e.actor_label or "system",
                 "metadata": e.metadata, "at": e.created_at.isoformat()} for e in qs]


class OpsUserStatusView(OpsAPIView):
    """POST /api/ops/users/<id>/status/ {action: deactivate|reactivate, reason}
    — routes through UserService (blocks login + revokes sessions + audits).
    Blocking a member's account touches their money access, so it requires a
    fresh step-up (OP-3)."""
    permission_classes = [RequireCapability("users.manage"), RequireStepUp]

    def post(self, request, user_id):
        from django.core.exceptions import ValidationError
        from apps.users.services import UserService

        u = get_object_or_404(User, pk=user_id, is_staff=False)
        action = (request.data.get("action") or "").strip()
        reason = (request.data.get("reason") or "").strip()

        try:
            if action == "deactivate":
                if not reason:
                    return Response({"detail": "A reason is required to deactivate."},
                                    status=http.HTTP_400_BAD_REQUEST)
                UserService.deactivate_user(u, reason=reason,
                                            actor_label=f"ops:{request.user.email}")
            elif action == "reactivate":
                UserService.reactivate_user(u, reason=reason,
                                            actor_label=f"ops:{request.user.email}")
            else:
                return Response({"detail": f"Unknown action: {action!r}."},
                                status=http.HTTP_400_BAD_REQUEST)
        except ValidationError as exc:
            detail = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
            return Response({"detail": detail}, status=http.HTTP_409_CONFLICT)

        record_action(
            action=f"ops.user.{action}", actor=request.user, request=request,
            target_type="user", target_id=u.pk, metadata={"reason": reason},
        )
        return Response({"id": u.pk, "is_active": u.is_active})
