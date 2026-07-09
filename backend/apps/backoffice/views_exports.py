"""Exports ops module (/api/ops/exports/, member statements) — OP-4.

Streamed-CSV exports for the registries operators already use, plus a per-member
statement. Every export is capability-gated and **writes an audit row** — data
egress is itself an auditable action. Rows stream via ``StreamingHttpResponse``
with a queryset iterator, so large ranges never buffer in memory; a row cap
bounds runaway queries (async generation into the files app is a follow-up).
"""
from __future__ import annotations

import csv
from datetime import datetime, time

from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .audit import record_action
from .permissions import RequireCapability
from .views import OpsAPIView

MAX_EXPORT_ROWS = 100_000


class _Echo:
    """A write-only file-like object that just returns what it's given — lets the
    csv writer stream row by row instead of building a buffer."""
    def write(self, value):
        return value


def _stream_csv(filename: str, header: list[str], rows) -> StreamingHttpResponse:
    writer = csv.writer(_Echo())

    def generate():
        yield writer.writerow(header)
        for row in rows:
            yield writer.writerow(row)

    resp = StreamingHttpResponse(generate(), content_type="text/csv")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


def _stamp(prefix: str) -> str:
    return f"{prefix}-{timezone.now():%Y%m%d-%H%M%S}.csv"


def _parse_date(value: str, *, end: bool):
    """Parse YYYY-MM-DD into an aware datetime (end-of-day for the upper bound)."""
    if not value:
        return None
    try:
        d = datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None
    return timezone.make_aware(datetime.combine(d, time.max if end else time.min))


class TransactionsExportView(OpsAPIView):
    """GET /api/ops/exports/transactions/?state=&op_type=&q= — the transaction
    register as CSV, mirroring the registry's filters."""
    permission_classes = [RequireCapability("reporting.export")]

    def get(self, request):
        from .views_transactions import _fund_of, filter_transactions

        p = request.query_params
        qs = filter_transactions(p)[:MAX_EXPORT_ROWS]

        record_action(
            action="ops.export.transactions", actor=request.user, request=request,
            metadata={"filters": {k: p.get(k) for k in ("state", "op_type", "q") if p.get(k)}})

        header = ["id", "created_at", "op_type", "state", "amount",
                  "initiated_by_phone", "recipient_phone", "fund", "mpesa_receipt",
                  "idempotency_key"]

        def rows():
            for ft in qs.iterator():
                fund_label, _ = _fund_of(ft)
                yield [
                    ft.id, ft.created_at.isoformat(), ft.op_type, ft.state, ft.amount,
                    ft.initiated_by.phone_number if ft.initiated_by_id else "",
                    ft.recipient_phone, fund_label or "", ft.mpesa_receipt or "",
                    ft.idempotency_key,
                ]

        return _stream_csv(_stamp("transactions"), header, rows())


class AuditExportView(OpsAPIView):
    """GET /api/ops/exports/audit/?action=&actor=&target_type=&target_id= — the
    audit trail as CSV, mirroring the audit viewer's filters."""
    permission_classes = [RequireCapability("audit.export")]

    def get(self, request):
        from apps.audit.models import AuditEvent

        p = request.query_params
        qs = AuditEvent.objects.all()
        if p.get("action"):
            qs = qs.filter(action__istartswith=p["action"].strip())
        if p.get("actor"):
            qs = qs.filter(actor_label__icontains=p["actor"].strip())
        if p.get("target_type"):
            qs = qs.filter(target_type__iexact=p["target_type"].strip())
        if p.get("target_id"):
            qs = qs.filter(target_id=p["target_id"].strip())
        qs = qs.order_by("-created_at")[:MAX_EXPORT_ROWS]

        record_action(
            action="ops.export.audit", actor=request.user, request=request,
            metadata={"filters": {k: p.get(k) for k in
                                  ("action", "actor", "target_type", "target_id") if p.get(k)}})

        header = ["id", "at", "action", "actor", "target_type", "target_id",
                  "ip_address", "metadata"]

        def rows():
            import json
            for e in qs.iterator():
                yield [e.id, e.created_at.isoformat(), e.action, e.actor_label or "system",
                       e.target_type, e.target_id, e.ip_address or "",
                       json.dumps(e.metadata, separators=(",", ":"))]

        return _stream_csv(_stamp("audit"), header, rows())


class MemberStatementExportView(OpsAPIView):
    """GET /api/ops/users/<id>/statement/?from=&to= — a member's sub-ledger
    journal lines for a period as CSV (their money movements, from the book of
    record). from/to are YYYY-MM-DD (inclusive), both optional."""
    permission_classes = [RequireCapability("ledger.export")]

    def get(self, request, user_id):
        from django.contrib.auth import get_user_model
        from apps.ledger.models import JournalLine

        User = get_user_model()
        member = get_object_or_404(User, pk=user_id, is_staff=False)

        p = request.query_params
        d_from = _parse_date(p.get("from", ""), end=False)
        d_to = _parse_date(p.get("to", ""), end=True)

        lines = (JournalLine.objects
                 .filter(account__owner=member)
                 .select_related("account", "journal"))
        if d_from:
            lines = lines.filter(journal__posted_at__gte=d_from)
        if d_to:
            lines = lines.filter(journal__posted_at__lte=d_to)
        lines = lines.order_by("journal__posted_at", "id")[:MAX_EXPORT_ROWS]

        record_action(
            action="ops.export.member_statement", actor=request.user, request=request,
            target_type="user", target_id=member.pk,
            metadata={"from": p.get("from"), "to": p.get("to")})

        header = ["posted_at", "entry_id", "op_type", "account_code", "account_name",
                  "direction", "amount", "narration"]

        def rows():
            for ln in lines.iterator():
                je = ln.journal
                yield [
                    je.posted_at.isoformat() if je.posted_at else "",
                    je.id, je.op_type, ln.account.code, ln.account.name,
                    ln.direction, ln.amount, je.narration or "",
                ]

        return _stream_csv(_stamp(f"statement-u{member.pk}"), header, rows())
