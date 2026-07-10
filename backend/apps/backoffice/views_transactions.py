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

from datetime import datetime, time
from decimal import Decimal, InvalidOperation

from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.response import Response

from apps.ledger.models import FinancialTransaction

from .permissions import RequireCapability
from .views import OpsAPIView

_REF_PREFIX = "WEPL-TXN-"
_FUND_FK = {"contribution": "contribution_id",
            "welfare": "welfare_fund_id",
            "shares": "shares_fund_id"}


def _ref_to_pk(q: str):
    """A bare id or a ``WEPL-TXN-000123`` reference → the FT id (else None).

    Plain string parsing (no regex) so a user-controlled search term can't drive
    catastrophic backtracking. ``int`` handles any leading zeros."""
    s = (q or "").strip()
    if s[:len(_REF_PREFIX)].upper() == _REF_PREFIX:
        s = s[len(_REF_PREFIX):]
    return int(s) if s.isdigit() else None


def _parse_date(value: str, *, end: bool):
    """YYYY-MM-DD → aware datetime (end-of-day for the upper bound); None if blank
    or unparseable, so a bad date is ignored rather than 500-ing the registry."""
    if not value:
        return None
    try:
        d = datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except (ValueError, AttributeError):
        return None
    return timezone.make_aware(datetime.combine(d, time.max if end else time.min))


def _parse_amount(value: str):
    try:
        return Decimal(value.strip()) if value else None
    except (InvalidOperation, AttributeError):
        return None


def _fund_of(ft):
    """(fund_label, community) for whichever fund FK is set."""
    if ft.contribution_id:
        return f"Pool · {ft.contribution.title}", ft.contribution.community
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
        # Registered M-Pesa name of the external counterparty (payer/recipient),
        # shown in full to operators. Blank for STK Push / internal movements.
        "counterparty_name": ft.counterparty_name,
        "fund": fund_label,
        "community_id": community.id if community else None,
        "mpesa_receipt": ft.mpesa_receipt,
        "created_at": ft.created_at.isoformat(),
    }


_SELECT = ("initiated_by", "contribution__community",
           "welfare_fund__community", "shares_fund__community")


def filter_transactions(params):
    """Shared registry filter — used by the list view and the CSV export so both
    honour the same query semantics. Every filter is optional and composable:
    state, op_type, free-text q, date range, amount range, fund/pool, and the
    ledger account a movement touched. The registry only ever returns what the
    filters ask for (paginated), never the whole table."""
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

    # Date range (on created_at), inclusive.
    d_from = _parse_date(params.get("date_from"), end=False)
    d_to = _parse_date(params.get("date_to"), end=True)
    if d_from:
        qs = qs.filter(created_at__gte=d_from)
    if d_to:
        qs = qs.filter(created_at__lte=d_to)

    # Amount range.
    a_min = _parse_amount(params.get("min"))
    a_max = _parse_amount(params.get("max"))
    if a_min is not None:
        qs = qs.filter(amount__gte=a_min)
    if a_max is not None:
        qs = qs.filter(amount__lte=a_max)

    # Fund / pool: transactions belonging to one pool (by its FK).
    fk = _FUND_FK.get((params.get("fund_type") or "").strip())
    fund_id = params.get("fund_id")
    if fk and fund_id and str(fund_id).isdigit():
        qs = qs.filter(**{fk: int(fund_id)})

    # Ledger account: every movement whose journal touched this account (by code)
    # — e.g. a member sub-ledger, a pool, Suspense, Fee Revenue, the float.
    account = (params.get("account") or "").strip()
    if account:
        qs = qs.filter(journals__lines__account__code=account).distinct()

    return qs.order_by("-created_at")


# Query params that count as "asking for something" (op_type/state below too).
_FILTER_KEYS = ("q", "account", "date_from", "date_to", "min", "max", "fund_id")


def _has_criteria(p) -> bool:
    """True when the operator asked for something specific. A bare list (no
    filter, state='all') is not a query — the registry is inquiry-first."""
    if any((p.get(k) or "").strip() for k in _FILTER_KEYS):
        return True
    if (p.get("op_type") or "").strip():
        return True
    if (p.get("state") or "all").strip() not in ("", "all"):
        return True
    return False


class TransactionsListView(OpsAPIView):
    """GET /api/ops/transactions/ — an inquiry, not a listing. Returns nothing
    until at least one criterion is given (state / op_type / q / account / date
    range / amount range / fund); then the matching movements, newest first,
    paginated. This is deliberate: at scale you query for what you need, you
    don't scroll the whole ledger."""
    permission_classes = [RequireCapability("transactions.view")]

    def get(self, request):
        p = request.query_params
        op_types = [{"value": v, "label": l}
                    for v, l in FinancialTransaction.OpType.choices]

        # Inquiry-first: no criteria → no results, just a prompt (and the static
        # op-type choices so the form can populate its dropdown). No DB query.
        if not _has_criteria(p):
            return Response({"results": [], "count": 0, "has_more": False,
                             "prompt": True, "op_types": op_types})

        qs = filter_transactions(p)
        try:
            limit = min(max(int(p.get("limit", 50)), 1), 100)
            offset = max(int(p.get("offset", 0)), 0)
        except (TypeError, ValueError):
            limit, offset = 50, 0
        total = qs.count()

        return Response({
            "results": [_row(ft) for ft in qs[offset:offset + limit]],
            "count": total, "has_more": offset + limit < total,
            "prompt": False, "op_types": op_types,
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
                # External counterparty's registered M-Pesa name (payer on a
                # pay-in, recipient on a payout) — full, for operators.
                "counterparty_name": ft.counterparty_name or None,
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
