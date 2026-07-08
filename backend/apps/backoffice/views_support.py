"""Support ops module (/api/ops/support/) — the verification-requests desk:
the ongoing-compliance rail (transaction documents, proof of address, KYC
supplements, clarifications) raised against members and answered from the
mobile Verification Center.

Reads compose directly; the two writes (raise, resolve) route through
UserService — the users domain's single door — which notifies on the durable
event bus and writes the domain audit trail.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status as http
from rest_framework.response import Response

from apps.users.models import VerificationRequest

from .audit import record_action
from .permissions import RequireCapability
from .views import OpsAPIView

User = get_user_model()


def _doc_url(vreq):
    if not vreq.document:
        return None
    try:
        if not vreq.document.storage.exists(vreq.document.name):
            return None
        return vreq.document.url
    except Exception:
        return None


def _row(v):
    return {
        "id": v.pk,
        "user_id": v.user_id,
        "user_name": v.user.name or "",
        "phone_number": v.user.phone_number,
        "kind": v.kind,
        "title": v.title,
        "status": v.status,
        "has_document": bool(v.document),
        "created_at": v.created_at.isoformat(),
        "responded_at": v.responded_at.isoformat() if v.responded_at else None,
    }


def _detail(v):
    return {
        **_row(v),
        "detail": v.detail,
        "response_note": v.response_note,
        "document_url": _doc_url(v),
        "review_note": v.review_note,
        "resolved_at": v.resolved_at.isoformat() if v.resolved_at else None,
        "kinds": [{"value": k, "label": l} for k, l in VerificationRequest.Kind.choices],
    }


class SupportRequestsView(OpsAPIView):
    """GET — the requests desk queue. POST {phone_number, kind, title, detail}
    — raise a new request against a member."""
    permission_classes = [RequireCapability("support.view")]

    def get(self, request):
        p = request.query_params
        qs = VerificationRequest.objects.select_related("user")
        status_filter = p.get("status", "open")
        if status_filter == "open":
            qs = qs.filter(status__in=(VerificationRequest.Status.OPEN,
                                       VerificationRequest.Status.SUBMITTED))
        elif status_filter != "all":
            qs = qs.filter(status=status_filter)
        if p.get("q"):
            q = p["q"].strip()
            qs = qs.filter(Q(user__phone_number__icontains=q)
                           | Q(user__name__icontains=q) | Q(title__icontains=q))
        # Answered items first — they're the ones waiting on staff.
        qs = qs.order_by("-responded_at", "-created_at")

        try:
            limit = min(max(int(p.get("limit", 50)), 1), 100)
            offset = max(int(p.get("offset", 0)), 0)
        except (TypeError, ValueError):
            limit, offset = 50, 0
        total = qs.count()
        return Response({
            "results": [_row(v) for v in qs[offset:offset + limit]],
            "count": total, "has_more": offset + limit < total,
            "kinds": [{"value": k, "label": l} for k, l in VerificationRequest.Kind.choices],
        })

    def post(self, request):
        from apps.users.services import UserService

        if not self._can_act(request):
            return Response({"detail": "You need the support.act capability."},
                            status=http.HTTP_403_FORBIDDEN)
        phone = (request.data.get("phone_number") or "").strip()
        member = User.objects.filter(phone_number=phone, is_staff=False).first()
        if member is None:
            return Response({"detail": "No member found with that phone number."},
                            status=http.HTTP_404_NOT_FOUND)
        try:
            vreq = UserService.raise_verification_request(
                member,
                kind=(request.data.get("kind") or "").strip(),
                title=(request.data.get("title") or "").strip(),
                detail=(request.data.get("detail") or "").strip(),
                actor_label=f"ops:{request.user.email}",
            )
        except ValidationError as exc:
            detail = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
            return Response({"detail": detail}, status=http.HTTP_400_BAD_REQUEST)
        record_action(
            action="ops.support.request_raised", actor=request.user, request=request,
            target_type="user", target_id=member.pk,
            metadata={"request_id": vreq.pk, "kind": vreq.kind, "title": vreq.title},
        )
        return Response(_detail(vreq), status=http.HTTP_201_CREATED)

    @staticmethod
    def _can_act(request) -> bool:
        from .capabilities import has_capability
        return has_capability(request.user, "support.act")


class SupportRequestDetailView(OpsAPIView):
    permission_classes = [RequireCapability("support.view")]

    def get(self, request, request_id):
        vreq = get_object_or_404(
            VerificationRequest.objects.select_related("user"), pk=request_id)
        return Response(_detail(vreq))


class SupportRequestResolveView(OpsAPIView):
    """POST … {note} — close the request with optional feedback to the member."""
    permission_classes = [RequireCapability("support.act")]

    def post(self, request, request_id):
        from apps.users.services import UserService

        vreq = get_object_or_404(
            VerificationRequest.objects.select_related("user"), pk=request_id)
        try:
            UserService.resolve_verification_request(
                vreq, note=(request.data.get("note") or ""),
                actor_label=f"ops:{request.user.email}",
            )
        except ValidationError as exc:
            detail = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
            return Response({"detail": detail}, status=http.HTTP_409_CONFLICT)
        record_action(
            action="ops.support.request_resolved", actor=request.user, request=request,
            target_type="user", target_id=vreq.user_id,
            metadata={"request_id": vreq.pk, "note": request.data.get("note", "")},
        )
        return Response(_detail(vreq))
