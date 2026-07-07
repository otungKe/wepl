"""Platform-wide console endpoints: the home-dashboard metrics and the
audit-log viewer. Each metric block is capability-filtered so an operator's
dashboard only carries numbers they may see.
"""
from __future__ import annotations

from django.utils import timezone
from rest_framework.response import Response

from .capabilities import has_capability
from .permissions import RequireCapability
from .views import OpsAPIView


def _age_hours(dt):
    if not dt:
        return None
    return round((timezone.now() - dt).total_seconds() / 3600, 1)


class OpsMetricsView(OpsAPIView):
    """GET /api/ops/metrics/ — real numbers for the home dashboard tiles.
    Blocks are included only when the operator holds the matching capability."""

    def get(self, request):
        u = request.user
        out = {}

        if has_capability(u, "verification.view"):
            from apps.users.models import KYCProfile
            from apps.verification.models import VerificationCase
            S = VerificationCase.State
            oldest = (KYCProfile.objects.filter(status="pending")
                      .order_by("submitted_at")
                      .values_list("submitted_at", flat=True).first())
            out["verification"] = {
                "kyc_pending": KYCProfile.objects.filter(status="pending").count(),
                "kyc_oldest_hours": _age_hours(oldest),
                "edd_open": VerificationCase.objects.exclude(
                    case_type=VerificationCase.CaseType.KYC_INDIVIDUAL
                ).filter(state__in=(S.SUBMITTED, S.REQUIRES_INFO)).count(),
            }

        if has_capability(u, "finops.view") or has_capability(u, "risk.view"):
            from apps.controls.models import HeldMovement
            out["holds"] = {
                "open": HeldMovement.objects.filter(status="OPEN").count(),
            }

        if has_capability(u, "health.view"):
            from apps.core.models import OutboxEvent
            oldest = (OutboxEvent.objects.filter(status="PENDING")
                      .order_by("created_at")
                      .values_list("created_at", flat=True).first())
            out["outbox"] = {
                "pending": OutboxEvent.objects.filter(status="PENDING").count(),
                "dead": OutboxEvent.objects.filter(status="DEAD").count(),
                "oldest_pending_seconds": (
                    round((timezone.now() - oldest).total_seconds()) if oldest else None),
            }

        if has_capability(u, "ledger.view"):
            from decimal import Decimal
            from apps.ledger.balances import trial_balance
            tb = trial_balance()
            debit = tb.get("total_debit") or Decimal("0")
            credit = tb.get("total_credit") or Decimal("0")
            out["ledger"] = {
                # 0 means the books balance; anything else is an incident.
                "trial_balance_delta": str(debit - credit),
                "balanced": bool(tb.get("balanced", debit == credit)),
            }

        if has_capability(u, "communities.view"):
            from apps.communities.models import Community
            out["communities"] = {
                "total": Community.objects.count(),
                "active": Community.objects.filter(status="active").count(),
                "suspended": Community.objects.filter(status="suspended").count(),
            }

        if has_capability(u, "users.view"):
            from django.contrib.auth import get_user_model
            User = get_user_model()
            week_ago = timezone.now() - timezone.timedelta(days=7)
            out["users"] = {
                "total": User.objects.filter(is_active=True).count(),
                "new_7d": User.objects.filter(date_joined__gte=week_ago).count(),
            }

        return Response(out)


class OpsAuditLogView(OpsAPIView):
    """GET /api/ops/audit/ — the append-only audit trail, filterable.

    Params: action (prefix match), actor (label contains), target_type,
    target_id, limit (≤100), offset.
    """
    permission_classes = [RequireCapability("audit.view")]

    def get(self, request):
        from apps.audit.models import AuditEvent

        qs = AuditEvent.objects.all()
        p = request.query_params
        if p.get("action"):
            qs = qs.filter(action__istartswith=p["action"].strip())
        if p.get("actor"):
            qs = qs.filter(actor_label__icontains=p["actor"].strip())
        if p.get("target_type"):
            qs = qs.filter(target_type__iexact=p["target_type"].strip())
        if p.get("target_id"):
            qs = qs.filter(target_id=p["target_id"].strip())

        try:
            limit = min(max(int(p.get("limit", 50)), 1), 100)
            offset = max(int(p.get("offset", 0)), 0)
        except (TypeError, ValueError):
            limit, offset = 50, 0

        total = qs.count()
        rows = [{
            "id": e.id,
            "action": e.action,
            "actor": e.actor_label or "system",
            "target_type": e.target_type,
            "target_id": e.target_id,
            "metadata": e.metadata,
            "ip_address": e.ip_address,
            "at": e.created_at.isoformat(),
        } for e in qs[offset:offset + limit]]
        return Response({"results": rows, "count": total,
                         "has_more": offset + limit < total})
