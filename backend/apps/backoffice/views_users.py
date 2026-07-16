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
                           | Q(member_number__icontains=q)
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
            "member_number": u.member_number,
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
        from apps.users.services import RestrictionService
        return Response({
            "identity": self._identity(u),
            "account_status": RestrictionService.account_status(u),
            "verification": self._verification(u),
            "restrictions": self._restrictions(u),
            "communities": self._communities(u),
            "financial": self._financial(u),
            "sessions": self._sessions(u),
            "audit_trail": self._audit(u),
        })

    @staticmethod
    def _restrictions(u):
        """Active restrictions first, then recent lifted/expired history."""
        from apps.users.models import UserRestriction
        rows = (UserRestriction.objects.filter(user=u)
                .order_by("-created_at")[:30])
        return [{
            "id": r.id, "kind": r.kind, "kind_label": r.get_kind_display(),
            "status": r.status, "is_effective": r.is_effective,
            "reason": r.reason,
            "effective_at": r.effective_at.isoformat(),
            "expires_at": r.expires_at.isoformat() if r.expires_at else None,
            "applied_by": r.applied_by_label,
            "lifted_at": r.lifted_at.isoformat() if r.lifted_at else None,
            "lifted_by": r.lifted_by_label,
        } for r in rows]

    @staticmethod
    def _identity(u):
        return {
            "id": u.pk, "member_number": u.member_number,
            "phone_number": u.phone_number, "name": u.name,
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
        from apps.ledger.models import Account

        positions = []
        total = Decimal("0")
        parts = (ContributionParticipant.objects
                 .filter(user=u, is_active=True)
                 .select_related("contribution")[:20])
        for part in parts:
            # Read-only: resolve the member's sub-ledger account if it exists (a
            # participant who never funded has none → zero). Never get-or-create
            # on a 360 view — a read must not mint chart-of-accounts rows.
            acct = Account.objects.filter(
                owner=u, fund_type="contribution", fund_id=part.contribution_id).first()
            bal = account_balance(acct) if acct else Decimal("0")
            total += bal
            positions.append({"contribution_id": part.contribution_id,
                              "name": part.contribution.title,
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
        from apps.users.services import PINService
        active = (UserSession.objects
                  .filter(user=u, revoked_at__isnull=True)
                  .order_by("-last_seen_at"))
        return {
            "active": active.count(),
            "pin_locked": PINService.is_locked(u),
            "devices": [{
                "sid": str(s.sid),
                "device_label": s.device_label,
                "ip_address": s.ip_address,
                "created": s.created_at.isoformat(),
                "last_seen": s.last_seen_at.isoformat(),
            } for s in active[:10]],
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


class OpsUserSessionsRevokeView(OpsAPIView):
    """POST /api/ops/users/<id>/sessions/revoke/ {sid} | {all: true, reason}
    — force sign-out of one device or every device (the stolen-phone response).
    Kills token refresh immediately via the session registry (ADR-0010).
    Touches account access → users.manage + fresh step-up."""
    permission_classes = [RequireCapability("users.manage"), RequireStepUp]

    def post(self, request, user_id):
        from apps.users import sessions as session_svc
        from apps.users.models import UserSession

        u = get_object_or_404(User, pk=user_id, is_staff=False)
        reason = (request.data.get("reason") or "").strip()

        if request.data.get("all"):
            count = session_svc.revoke_all_for_user(u)
            record_action(action="ops.user.sessions_revoke_all", actor=request.user,
                          request=request, target_type="user", target_id=u.pk,
                          metadata={"revoked": count, "reason": reason})
            return Response({"revoked": count})

        sid = (request.data.get("sid") or "").strip()
        if not sid:
            return Response({"detail": "Provide a sid or all: true."},
                            status=http.HTTP_400_BAD_REQUEST)
        session = UserSession.objects.filter(
            sid=sid, user=u, revoked_at__isnull=True).first()
        if not session:
            return Response({"detail": "Active session not found."},
                            status=http.HTTP_404_NOT_FOUND)
        session_svc.revoke(session)
        record_action(action="ops.user.session_revoke", actor=request.user,
                      request=request, target_type="user", target_id=u.pk,
                      metadata={"sid": sid, "device": session.device_label,
                                "reason": reason})
        return Response({"revoked": 1, "sid": sid})


class OpsUserUnlockPinView(OpsAPIView):
    """POST /api/ops/users/<id>/unlock-pin/ — clear the member's PIN lockout
    counters so they can try again (the "locked out at the market" support
    call). Does NOT change or reveal the PIN."""
    permission_classes = [RequireCapability("users.manage")]

    def post(self, request, user_id):
        from apps.users.services import PINService

        u = get_object_or_404(User, pk=user_id, is_staff=False)
        was_locked = PINService.is_locked(u)
        PINService.clear_failures(u)
        record_action(action="ops.user.unlock_pin", actor=request.user,
                      request=request, target_type="user", target_id=u.pk,
                      metadata={"was_locked": was_locked})
        return Response({"unlocked": True, "was_locked": was_locked})


class OpsUserProfileView(OpsAPIView):
    """POST /api/ops/users/<id>/profile/ {name} — correct the display name (a
    typo fix is routine support work; identity documents stay the KYC module's
    job). Audited with before/after."""
    permission_classes = [RequireCapability("users.manage")]

    def post(self, request, user_id):
        u = get_object_or_404(User, pk=user_id, is_staff=False)
        name = (request.data.get("name") or "").strip()
        if not name or len(name) > 150:
            return Response({"detail": "Provide a name (max 150 chars)."},
                            status=http.HTTP_400_BAD_REQUEST)
        before = u.name
        if name == before:
            return Response({"id": u.pk, "name": u.name})
        u.name = name
        u.save(update_fields=["name"])
        record_action(action="ops.user.profile_correct", actor=request.user,
                      request=request, target_type="user", target_id=u.pk,
                      metadata={"field": "name", "before": before, "after": name})
        return Response({"id": u.pk, "name": u.name})


class OpsUserNoteView(OpsAPIView):
    """POST /api/ops/users/<id>/notes/ {note} — attach a support note to the
    member. Notes are audit events (append-only, actor-stamped) so they show in
    the 360 trail and the global audit browser with zero new storage."""
    permission_classes = [RequireCapability("users.view")]

    def post(self, request, user_id):
        u = get_object_or_404(User, pk=user_id, is_staff=False)
        note = (request.data.get("note") or "").strip()
        if not note or len(note) > 2000:
            return Response({"detail": "Provide a note (max 2000 chars)."},
                            status=http.HTTP_400_BAD_REQUEST)
        record_action(action="ops.user.note", actor=request.user, request=request,
                      target_type="user", target_id=u.pk, metadata={"note": note})
        return Response({"noted": True})


class OpsUserPhoneChangeRequestView(OpsAPIView):
    """POST /api/ops/users/<id>/phone-change-request/ {new_phone, reason}
    — raise a maker-checker request to change the member's phone number.
    The phone IS the login identity and the M-Pesa payout address, i.e. the
    SIM-swap fraud vector — never single-handed (OP-3). A second operator
    approves from the Approvals inbox; execution swaps the number and revokes
    every session. users.manage + step-up to request."""
    permission_classes = [RequireCapability("users.manage"), RequireStepUp]

    def post(self, request, user_id):
        from django.core.exceptions import ValidationError
        from . import approvals
        from .flagged_actions import ACTION_PHONE_CHANGE

        u = get_object_or_404(User, pk=user_id, is_staff=False)
        new_phone = (request.data.get("new_phone") or "").strip()
        reason = (request.data.get("reason") or "").strip()

        import re
        if not re.fullmatch(r"\+?254(7|1)\d{8}", new_phone):
            return Response({"detail": "new_phone must be a valid Kenyan number (2547XXXXXXXX)."},
                            status=http.HTTP_400_BAD_REQUEST)
        if User.objects.filter(phone_number=new_phone).exists():
            return Response({"detail": "That phone number already belongs to an account."},
                            status=http.HTTP_409_CONFLICT)

        try:
            appr = approvals.require_approval(
                ACTION_PHONE_CHANGE,
                params={"user_id": u.pk, "old_phone": u.phone_number,
                        "new_phone": new_phone, "reason": reason},
                actor=request.user, reason=reason, target_id=str(u.pk))
        except ValidationError as exc:
            detail = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
            return Response({"detail": detail}, status=http.HTTP_409_CONFLICT)

        record_action(action="ops.user.phone_change_requested", actor=request.user,
                      request=request, target_type="user", target_id=u.pk,
                      metadata={"new_phone": new_phone, "approval_id": appr.pk,
                                "reason": reason})
        return Response({"approval_id": appr.pk, "status": "pending_approval"},
                        status=http.HTTP_202_ACCEPTED)


class OpsUserRestrictionApplyView(OpsAPIView):
    """POST /api/ops/users/<id>/restrictions/ {kind, reason, expires_at?}
    — place an account restriction. Each kind is enforced at a real chokepoint
    (login / the money control gate). Touches account + money access →
    users.manage + fresh step-up; a reason is mandatory; every apply is audited."""
    permission_classes = [RequireCapability("users.manage"), RequireStepUp]

    def post(self, request, user_id):
        from django.core.exceptions import ValidationError
        from django.utils.dateparse import parse_datetime
        from apps.users.services import RestrictionService

        u = get_object_or_404(User, pk=user_id, is_staff=False)
        kind = (request.data.get("kind") or "").strip()
        reason = (request.data.get("reason") or "").strip()

        expires_at = None
        raw_exp = request.data.get("expires_at")
        if raw_exp:
            expires_at = parse_datetime(raw_exp)
            if expires_at is None:
                return Response({"detail": "expires_at must be an ISO-8601 datetime."},
                                status=http.HTTP_400_BAD_REQUEST)

        try:
            r = RestrictionService.apply(
                u, kind, reason=reason, expires_at=expires_at,
                actor_label=f"ops:{request.user.email}")
        except ValidationError as exc:
            detail = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
            return Response({"detail": detail}, status=http.HTTP_400_BAD_REQUEST)

        record_action(action="ops.user.restrict", actor=request.user, request=request,
                      target_type="user", target_id=u.pk,
                      metadata={"kind": kind, "reason": reason,
                                "expires_at": r.expires_at.isoformat() if r.expires_at else None,
                                "restriction_id": r.id})
        return Response({"id": r.id, "kind": r.kind, "status": r.status},
                        status=http.HTTP_201_CREATED)


class OpsUserRestrictionLiftView(OpsAPIView):
    """POST /api/ops/users/<id>/restrictions/<rid>/lift/ {reason?}
    — lift an active restriction. users.manage + step-up; audited."""
    permission_classes = [RequireCapability("users.manage"), RequireStepUp]

    def post(self, request, user_id, restriction_id):
        from django.core.exceptions import ValidationError
        from apps.users.models import UserRestriction
        from apps.users.services import RestrictionService

        r = get_object_or_404(UserRestriction, pk=restriction_id, user_id=user_id)
        try:
            RestrictionService.lift(
                r, reason=(request.data.get("reason") or "").strip(),
                actor_label=f"ops:{request.user.email}")
        except ValidationError as exc:
            detail = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
            return Response({"detail": detail}, status=http.HTTP_409_CONFLICT)

        record_action(action="ops.user.restriction_lift", actor=request.user,
                      request=request, target_type="user", target_id=int(user_id),
                      metadata={"kind": r.kind, "restriction_id": r.id})
        return Response({"id": r.id, "status": r.status})
