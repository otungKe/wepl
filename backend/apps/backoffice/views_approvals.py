"""Approvals ops module (/api/ops/approvals/) — the maker-checker inbox
(OP-3 Part 2).

A checker sees pending dual-control requests, then approves (which executes the
flagged action, attributed to both operators) or rejects. Deciding requires
``approvals.decide`` + a fresh step-up, and a request can never be approved by
the operator who raised it.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from rest_framework import status as http
from rest_framework.response import Response

from . import approvals
from .audit import record_action
from .models import OpsApprovalRequest
from .permissions import RequireCapability, RequireStepUp
from .views import OpsAPIView


def _row(a: OpsApprovalRequest) -> dict:
    status = OpsApprovalRequest.Status.EXPIRED if a.is_expired else a.status
    return {
        "id": a.pk,
        "action": a.action,
        "summary": a.summary,
        "reason": a.reason,
        "status": status,
        "target_type": a.target_type,
        "target_id": a.target_id,
        "requested_by": a.requested_by.full_name or a.requested_by.email,
        "requested_by_email": a.requested_by.email,
        "requested_at": a.requested_at.isoformat(),
        "expires_at": a.expires_at.isoformat(),
        "decided_by": (a.decided_by.full_name or a.decided_by.email) if a.decided_by_id else None,
        "decided_at": a.decided_at.isoformat() if a.decided_at else None,
        "decision_note": a.decision_note,
        "result": a.result,
    }


class ApprovalsListView(OpsAPIView):
    """GET /api/ops/approvals/?status=pending — the checker's inbox (pending by
    default), newest first."""
    permission_classes = [RequireCapability("approvals.view")]

    def get(self, request):
        status = (request.query_params.get("status") or "pending").upper()
        qs = OpsApprovalRequest.objects.select_related("requested_by", "decided_by")
        if status != "ALL":
            qs = qs.filter(status=status)
        rows = [_row(a) for a in qs[:100]]
        counts = {"pending": OpsApprovalRequest.objects.filter(
            status=OpsApprovalRequest.Status.PENDING).count()}
        return Response({"results": rows, "counts": counts})


class ApprovalDetailView(OpsAPIView):
    """GET /api/ops/approvals/<id>/ — one request with full context."""
    permission_classes = [RequireCapability("approvals.view")]

    def get(self, request, request_id):
        a = get_object_or_404(
            OpsApprovalRequest.objects.select_related("requested_by", "decided_by"),
            pk=request_id)
        return Response({**_row(a), "params": a.params})


class ApprovalDecideView(OpsAPIView):
    """POST /api/ops/approvals/<id>/decide/ {decision: approve|reject, note}
    — the second-operator decision. approvals.decide + step-up; self-approval
    refused; approval executes the flagged action attributed to both."""
    permission_classes = [RequireCapability("approvals.decide"), RequireStepUp]

    def post(self, request, request_id):
        decision = (request.data.get("decision") or "").strip().lower()
        note = (request.data.get("note") or "").strip()
        if decision not in ("approve", "reject"):
            return Response({"detail": "decision must be 'approve' or 'reject'."},
                            status=http.HTTP_400_BAD_REQUEST)
        try:
            appr = approvals.decide(
                request_id, checker=request.user,
                approve=(decision == "approve"), note=note)
        except OpsApprovalRequest.DoesNotExist:
            return Response({"detail": "Request not found."}, status=http.HTTP_404_NOT_FOUND)
        except ValidationError as exc:
            detail = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
            return Response({"detail": detail}, status=http.HTTP_409_CONFLICT)

        record_action(
            action=f"ops.approval.{decision}", actor=request.user, request=request,
            target_type="approval_request", target_id=appr.pk,
            metadata={"flagged_action": appr.action, "status": appr.status,
                      "requested_by": appr.requested_by.email},
        )
        return Response(_row(appr))
