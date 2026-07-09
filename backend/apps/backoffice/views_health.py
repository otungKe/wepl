"""System Health ops module (/api/ops/health/) + the alert bell (/api/ops/notices/)
— OP-2.

Health surfaces the async nervous system: the outbox (with a dead-letter browser
and requeue), worker heartbeats, and Celery queue depths. The bell surfaces
``StaffNotice`` alerts raised by the ``ops_alerts`` task to every operator.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status as http
from rest_framework.response import Response

from apps.core.models import OutboxEvent

from .audit import record_action
from .models import StaffNotice
from .permissions import RequireCapability
from .views import OpsAPIView


class HealthOverviewView(OpsAPIView):
    """GET /api/ops/health/ — outbox summary, worker heartbeats, queue depths."""
    permission_classes = [RequireCapability("health.view")]

    def get(self, request):
        from apps.core.health import heartbeats, queue_depths

        oldest = (OutboxEvent.objects.filter(status=OutboxEvent.Status.PENDING)
                  .order_by("created_at").values_list("created_at", flat=True).first())
        outbox = {
            "pending": OutboxEvent.objects.filter(status=OutboxEvent.Status.PENDING).count(),
            "dead": OutboxEvent.objects.filter(status=OutboxEvent.Status.DEAD).count(),
            "oldest_pending_seconds": (
                round((timezone.now() - oldest).total_seconds()) if oldest else None),
        }
        return Response({
            "outbox": outbox,
            "heartbeats": heartbeats(),
            "queues": queue_depths(),
        })


class OutboxListView(OpsAPIView):
    """GET /api/ops/health/outbox/?status=DEAD&limit=&offset= — browse events,
    dead-letters first by default, with payload + last_error for triage."""
    permission_classes = [RequireCapability("health.view")]

    def get(self, request):
        p = request.query_params
        status = (p.get("status") or "DEAD").upper()
        qs = OutboxEvent.objects.all()
        if status != "ALL":
            qs = qs.filter(status=status)
        qs = qs.order_by("-id")
        try:
            limit = min(max(int(p.get("limit", 50)), 1), 100)
            offset = max(int(p.get("offset", 0)), 0)
        except (TypeError, ValueError):
            limit, offset = 50, 0
        total = qs.count()
        rows = [{
            "id": e.id,
            "event_type": e.event_type,
            "status": e.status,
            "attempts": e.attempts,
            "last_error": e.last_error,
            "payload": e.payload,
            "created_at": e.created_at.isoformat(),
            "processed_at": e.processed_at.isoformat() if e.processed_at else None,
        } for e in qs[offset:offset + limit]]
        return Response({"results": rows, "count": total, "has_more": offset + limit < total})


class OutboxRequeueView(OpsAPIView):
    """POST /api/ops/health/outbox/<id>/requeue/ — return a dead-lettered event to
    the delivery queue (health.act, audited). Routes through the core service door."""
    permission_classes = [RequireCapability("health.act")]

    def post(self, request, event_id):
        from apps.core.events import requeue_outbox_event
        try:
            event = requeue_outbox_event(event_id)
        except OutboxEvent.DoesNotExist:
            return Response({"detail": "Event not found."}, status=http.HTTP_404_NOT_FOUND)
        except ValidationError as exc:
            detail = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
            return Response({"detail": detail}, status=http.HTTP_409_CONFLICT)

        record_action(
            action="ops.health.outbox_requeued", actor=request.user, request=request,
            target_type="outbox_event", target_id=event.id,
            metadata={"event_type": event.event_type})
        return Response({"id": event.id, "status": event.status})


# ── Alert bell ────────────────────────────────────────────────────────────────
def _notice_row(n: StaffNotice) -> dict:
    return {
        "id": n.id, "key": n.key, "level": n.level,
        "title": n.title, "message": n.message,
        "created_at": n.created_at.isoformat(),
    }


class NoticesView(OpsAPIView):
    """GET /api/ops/notices/ — open operational alerts for the console bell.
    Any operator sees these (no extra capability); acting on them is gated
    elsewhere."""

    def get(self, request):
        qs = StaffNotice.objects.filter(resolved_at__isnull=True, dismissed_at__isnull=True)
        rows = [_notice_row(n) for n in qs[:50]]
        return Response({
            "results": rows,
            "count": len(rows),
            "critical": sum(1 for r in rows if r["level"] == "CRITICAL"),
        })


class NoticeDismissView(OpsAPIView):
    """POST /api/ops/notices/<id>/dismiss/ — acknowledge a notice (hides it from
    the bell). If the underlying condition persists, ops_alerts will raise it
    again on its next run."""

    def post(self, request, notice_id):
        n = get_object_or_404(StaffNotice, pk=notice_id)
        if n.is_open:
            n.dismissed_at = timezone.now()
            n.dismissed_by = request.user
            n.save(update_fields=["dismissed_at", "dismissed_by"])
            record_action(action="ops.notice.dismissed", actor=request.user, request=request,
                          target_type="staff_notice", target_id=n.id, metadata={"key": n.key})
        return Response({"id": n.id, "dismissed": True})
