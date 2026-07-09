"""Transactions ops module (/api/ops/transactions/) — the money-movement
registry and the Transaction 360.

Read-only by design: a FinancialTransaction's state machine belongs to the
payment pipeline (transition_to + callbacks), and its money truth is the
journal. This module *shows* both, side by side — the movement record, the
control decisions that examined it, and (for operators holding ledger.view)
the journal entries and balanced lines behind it. Operational levers (retry,
reversal) arrive with the FinOps module once the payments domain exposes a
service door for them; a viewer will never be given a button that bypasses
the pipeline.
"""
from __future__ import annotations

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework.response import Response

_REF_PREFIX = "WEPL-TXN-"


def _ref_to_pk(q: str):
    """A bare id or a ``WEPL-TXN-000123`` reference → the FT id (else None).

    Plain string parsing (no regex) so a user-controlled search term can't drive
    catastrophic backtracking. ``int`` handles any leading zeros."""
    s = (q or "").strip()
    if s[:len(_REF_PREFIX)].upper() == _REF_PREFIX:
        s = s[len(_REF_PREFIX):]
    return int(s) if s.isdigit() else None

from apps.ledger.models import FinancialTransaction

from .permissions import RequireCapability
from .views import OpsAPIView


def _fund_of(ft):
    """(fund_label, community) for whichever fund FK is set."""
    if ft.contribution_id:
        return f"Pool · {ft.contribution.name}", ft.contribution.community
    if ft.welfare_fund_id:
        return f"Welfare · {ft.welfare_fund.name}", ft.welfare_fund.community
    if ft.shares_fund_id:
        return f"Shares · {ft.shares_fund.name}", ft.shares_fund.community
    return None, None


def _row(ft):
    fund_label, community = _fund_of(ft)
    return {
        "id": ft.pk,
        "reference": ft.reference,
        "op_type": ft.op_type,
        "state": ft.state,
        "amount": str(ft.amount),
        "initiated_by_id": ft.initiated_by_id,
        "initiated_by": (ft.initiated_by.name or ft.initiated_by.phone_number
                         if ft.initiated_by_id else "system"),
        "recipient_phone": ft.recipient_phone,
        "fund": fund_label,
        "community_id": community.id if community else None,
        "mpesa_receipt": ft.mpesa_receipt,
        "created_at": ft.created_at.isoformat(),
    }


_SELECT = ("initiated_by", "contribution__community",
           "welfare_fund__community", "shares_fund__community")


def filter_transactions(params):
    """Shared registry filter (state / op_type / q) — used by the list view and
    the CSV export so both honour the same query semantics."""
    qs = FinancialTransaction.objects.select_related(*_SELECT)
    if params.get("state") and params["state"] != "all":
        qs = qs.filter(state=params["state"])
    if params.get("op_type"):
        qs = qs.filter(op_type=params["op_type"])
    if params.get("q"):
        q = params["q"].strip()
        pk = _ref_to_pk(q)   # bare id or WEPL-TXN-000123 → FT id
        qs = qs.filter(
            Q(initiated_by__phone_number__icontains=q)
            | Q(recipient_phone__icontains=q)
            | Q(idempotency_key__iexact=q)
            | Q(mpesa_receipt__iexact=q)
            | (Q(pk=pk) if pk is not None else Q()))
    return qs.order_by("-created_at")


class TransactionsListView(OpsAPIView):
    """GET /api/ops/transactions/?state=&op_type=&q=&limit=&offset= — the
    registry, newest first, with state counts for the current filter set."""
    permission_classes = [RequireCapability("transactions.view")]

    def get(self, request):
        p = request.query_params
        qs = filter_transactions(p)

        try:
            limit = min(max(int(p.get("limit", 50)), 1), 100)
            offset = max(int(p.get("offset", 0)), 0)
        except (TypeError, ValueError):
            limit, offset = 50, 0
        total = qs.count()

        # State mix for the whole (unpaginated, state-agnostic) filter — the
        # tabs' badge numbers.
        base = FinancialTransaction.objects.all()
        if p.get("op_type"):
            base = base.filter(op_type=p["op_type"])
        by_state = {r["state"]: r["c"] for r in
                    base.values("state").annotate(c=Count("id"))}

        return Response({
            "results": [_row(ft) for ft in qs[offset:offset + limit]],
            "count": total, "has_more": offset + limit < total,
            "by_state": by_state,
            "op_types": [{"value": v, "label": l}
                         for v, l in FinancialTransaction.OpType.choices],
        })


class Transaction360View(OpsAPIView):
    """GET /api/ops/transactions/<id>/ — the Transaction 360: the movement,
    its parties and fund context, the control decisions that examined it, and
    the double-entry journal behind it — which accounts were debited and
    credited (shown to any transactions.view holder)."""
    permission_classes = [RequireCapability("transactions.view")]

    def get(self, request, tx_id):
        ft = get_object_or_404(
            FinancialTransaction.objects.select_related(*_SELECT), pk=tx_id)
        fund_label, community = _fund_of(ft)

        payload = {
            "movement": {
                "id": ft.pk,
                "reference": ft.reference,
                "op_type": ft.op_type,
                "op_type_label": ft.get_op_type_display(),
                "state": ft.state,
                "amount": str(ft.amount),
                "idempotency_key": ft.idempotency_key,
                "note": ft.note,
                "failure_reason": ft.failure_reason,
                "created_at": ft.created_at.isoformat(),
                "updated_at": ft.updated_at.isoformat(),
            },
            "parties": {
                "initiated_by_id": ft.initiated_by_id,
                "initiated_by": (ft.initiated_by.name or ft.initiated_by.phone_number
                                 if ft.initiated_by_id else "system"),
                "initiated_by_phone": (ft.initiated_by.phone_number
                                       if ft.initiated_by_id else None),
                "initiated_by_member_no": (ft.initiated_by.member_number
                                           if ft.initiated_by_id else None),
                "recipient_phone": ft.recipient_phone,
            },
            "context": {
                "fund": fund_label,
                "community_id": community.id if community else None,
                "community_name": community.name if community else None,
                "trigger_type": ft.context_type,
                "trigger_id": ft.context_id,
            },
            "rail": {
                "mpesa_checkout_id": ft.mpesa_checkout_id,
                "mpesa_conversation_id": ft.mpesa_conversation_id,
                "mpesa_receipt": ft.mpesa_receipt,
            },
            "controls": self._controls(ft),
            # The accounting truth of THIS movement — which accounts were debited
            # and credited. Shown to anyone who may view the transaction: a
            # movement without its double-entry is only half the story. (Browsing
            # the whole ledger / trial balance stays gated behind ledger.view.)
            "journal": self._journal(ft),
        }
        return Response(payload)

    @staticmethod
    def _controls(ft):
        from apps.controls.models import ControlDecision
        return [{
            "decision": d.decision, "reason": d.reason,
            "rule": d.rule.name if d.rule_id else None,
            "at": d.created_at.isoformat(),
        } for d in (ControlDecision.objects.select_related("rule")
                    .filter(financial_transaction=ft).order_by("-created_at")[:10])]

    @staticmethod
    def _journal(ft):
        entries = []
        for j in ft.journals.prefetch_related("lines__account").order_by("posted_at"):
            entries.append({
                "id": j.pk,
                "narration": j.narration,
                "posted_at": j.posted_at.isoformat() if j.posted_at else None,
                "reverses_id": j.reverses_id,
                "lines": [{
                    "account_code": ln.account.code,
                    "account_name": ln.account.name,
                    "direction": ln.direction,
                    "amount": str(ln.amount),
                } for ln in j.lines.all()],
            })
        return entries
