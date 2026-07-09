"""FinOps ops module (/api/ops/finops/) — the payments desk's recovery levers
(OP-1).

Read side: three queues that frame the desk's day — stuck payouts (money going
out that stalled), failed payouts, and a count of stuck pay-ins (which recover on
their own rail). Write side: per-movement requery / mark-failed, routed through
``PaymentOpsService`` (the one door — no button bypasses the pipeline) and gated
behind ``finops.retry`` + a fresh step-up, with a dual audit trail.
"""
from __future__ import annotations

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status as http
from rest_framework.response import Response

from apps.ledger.models import FinancialTransaction as FT
from apps.payments.ops import PAYOUT_OP_TYPES, PaymentOpsService

from .audit import record_action
from .permissions import RequireCapability, RequireStepUp
from .views import OpsAPIView
from .views_transactions import _SELECT, _row

# A movement older than this in an open state is "stuck" and worth a look.
STUCK_AFTER = timedelta(minutes=30)
_OPEN = (FT.State.PENDING, FT.State.PROCESSING)


class FinopsQueuesView(OpsAPIView):
    """GET /api/ops/finops/?minutes=30 — the desk's queues + headline counts."""
    permission_classes = [RequireCapability("finops.view")]

    def get(self, request):
        try:
            minutes = max(0, int(request.query_params.get("minutes", 30)))
        except (TypeError, ValueError):
            minutes = 30
        cutoff = timezone.now() - timedelta(minutes=minutes)

        payouts = FT.objects.filter(op_type__in=PAYOUT_OP_TYPES)
        stuck = (payouts.filter(state__in=_OPEN, created_at__lte=cutoff)
                 .select_related(*_SELECT).order_by("created_at"))
        failed = (payouts.filter(state=FT.State.FAILED)
                  .select_related(*_SELECT).order_by("-updated_at")[:100])

        # Pay-ins are MpesaSTKRequest rows, auto-requeried by poll_mpesa_stk_status.
        from apps.mpesa.models import MpesaSTKRequest
        stuck_payins = MpesaSTKRequest.objects.filter(
            status="PENDING", created_at__lte=cutoff).count()

        return Response({
            "threshold_minutes": minutes,
            "counts": {
                "stuck_payouts": stuck.count(),
                "failed_payouts": payouts.filter(state=FT.State.FAILED).count(),
                "stuck_payins": stuck_payins,
            },
            "stuck_payouts": [_finops_row(ft) for ft in stuck],
            "failed_payouts": [_finops_row(ft) for ft in failed],
        })


class FinopsActionView(OpsAPIView):
    """POST /api/ops/finops/transactions/<ft_id>/action/ {action, reason}
    — action ∈ {requery, mark_failed}. Routes through PaymentOpsService; every
    call is step-up-gated and written to the ops audit log with its outcome."""
    permission_classes = [RequireCapability("finops.retry"), RequireStepUp]

    def post(self, request, ft_id):
        ft = get_object_or_404(FT, pk=ft_id)
        action = (request.data.get("action") or "").strip()
        reason = (request.data.get("reason") or "").strip()
        actor_label = f"ops:{request.user.email}"

        try:
            if action == "requery":
                result = PaymentOpsService.requery(ft, actor_label=actor_label)
            elif action == "mark_failed":
                result = PaymentOpsService.mark_failed(ft, reason=reason, actor_label=actor_label)
            else:
                return Response({"detail": f"Unknown action: {action!r}."},
                                status=http.HTTP_400_BAD_REQUEST)
        except ValidationError as exc:
            detail = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
            return Response({"detail": detail}, status=http.HTTP_409_CONFLICT)

        record_action(
            action=f"ops.finops.{action}", actor=request.user, request=request,
            target_type="financial_transaction", target_id=ft.pk,
            metadata={"outcome": result["outcome"], "state": result["state"],
                      "reason": reason} if reason else
                     {"outcome": result["outcome"], "state": result["state"]},
        )
        ft.refresh_from_db()
        return Response({**_finops_row(ft), "result": result})


def _finops_row(ft) -> dict:
    """A transactions row plus the fields the desk triages on."""
    return {
        **_row(ft),
        "updated_at": ft.updated_at.isoformat(),
        "failure_reason": ft.failure_reason,
        "conversation_id": ft.mpesa_conversation_id,
        "recipient_phone": ft.recipient_phone,
    }
