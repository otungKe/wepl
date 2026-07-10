"""Accounts ops module (/api/ops/accounts/) — the Chart-of-Accounts browser.

The account-search surface for ADR-0025: one searchable namespace over the whole
tree — GL heads, pool control accounts, and member sub-ledgers — queried on the
indexed structured columns (owner, fund_type/fund_id, type, parent). Read-only:
a search must never mint a chart-of-accounts row, so this resolves existing
`Account`s only (never get-or-create) and reads balances from the projection.

Inquiry-first, like the transactions registry: nothing is returned until at
least one criterion is given. At millions of sub-ledgers you query for the
account you want — you do not scroll the book.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.shortcuts import get_object_or_404

from rest_framework.response import Response

from apps.ledger.balances import account_balance
from apps.ledger.models import Account

from .permissions import RequireCapability
from .views import OpsAPIView

User = get_user_model()

# fund_type → the GL head its accounts hang off (the code prefix). Mirrors
# coa._FUND_GL without importing it, to keep the ops layer decoupled from COA
# internals; used to label rows and offer the fund-type facet.
_FUND_GL = {
    "contribution": "2000",
    "welfare": "2100",
    "shares": "2200",
    "advance": "1200",
}


def _resolve_owner(term: str):
    """A member handle (bare id, phone, or member number) → user id, else None."""
    term = (term or "").strip()
    if not term:
        return None
    cond = Q(phone_number__icontains=term) | Q(member_number__iexact=term)
    if term.isdigit():
        cond |= Q(pk=term)
    return (User.objects.filter(cond).values_list("pk", flat=True).first())


def _classify(acct: Account) -> str:
    """Which of the three account roles this row is (ADR-0025)."""
    if acct.owner_id is not None:
        return "member"          # a member sub-ledger
    if acct.fund_type:
        return "pool"            # a pool/fund control account
    return "gl"                  # a canonical GL head


def filter_accounts(params):
    """Shared account filter — used by the browser (and any future export) so
    both honour the same query semantics. Every filter is optional and composable
    and lands on an indexed column: free-text code/name, member owner, fund
    (type + id), account type, and parent GL head. Ordered by code so the tree
    reads top-down."""
    qs = Account.objects.select_related("parent", "owner")

    # Free text: the account code (the thing operators quote) or its name.
    if params.get("q"):
        q = params["q"].strip()
        qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q))

    # Member owner — resolve a member handle to the owner id.
    owner_term = (params.get("owner") or "").strip()
    if owner_term:
        owner_id = _resolve_owner(owner_term)
        # Unresolvable handle → no accounts (rather than every account).
        qs = qs.filter(owner_id=owner_id) if owner_id else qs.none()

    # Fund (type and/or id) — the pool and all its member sub-ledgers.
    ft = (params.get("fund_type") or "").strip()
    if ft:
        qs = qs.filter(fund_type=ft)
    fund_id = params.get("fund_id")
    if fund_id and str(fund_id).isdigit():
        qs = qs.filter(fund_id=int(fund_id))

    # Account type (ASSET / LIABILITY / …).
    acct_type = (params.get("type") or "").strip().upper()
    if acct_type in Account.Type.values:
        qs = qs.filter(type=acct_type)

    # GL head — accounts sitting under one GL control account, by that GL's code
    # (e.g. gl=2000 → the contributions pools and their members).
    gl = (params.get("gl") or "").strip()
    if gl:
        qs = qs.filter(Q(code=gl) | Q(parent__code=gl) | Q(parent__parent__code=gl))

    # Role facet: gl | pool | member.
    role = (params.get("role") or "").strip()
    if role == "member":
        qs = qs.filter(owner__isnull=False)
    elif role == "pool":
        qs = qs.filter(owner__isnull=True).exclude(fund_type="")
    elif role == "gl":
        qs = qs.filter(owner__isnull=True, fund_type="")

    return qs.order_by("code")


# Query params that count as "asking for something".
_FILTER_KEYS = ("q", "owner", "fund_type", "fund_id", "type", "gl", "role")


def _has_criteria(p) -> bool:
    """True when the operator asked for something specific — inquiry-first."""
    return any((p.get(k) or "").strip() for k in _FILTER_KEYS)


def _row(acct: Account) -> dict:
    return {
        "id": acct.pk,
        "account_uid": str(acct.account_uid) if acct.account_uid else None,
        "code": acct.code,
        "name": acct.name,
        "type": acct.type,
        "role": _classify(acct),
        "fund_type": acct.fund_type or None,
        "fund_id": acct.fund_id,
        "owner_id": acct.owner_id,
        "owner": (acct.owner.name or acct.owner.phone_number) if acct.owner_id else None,
        "owner_member_no": acct.owner.member_number if acct.owner_id else None,
        "parent_code": acct.parent.code if acct.parent_id else None,
        "balance": str(account_balance(acct)),
        "currency": acct.currency,
        "is_active": acct.is_active,
    }


class AccountsSearchView(OpsAPIView):
    """GET /api/ops/accounts/ — the Chart-of-Accounts browser. An inquiry, not a
    listing: returns nothing until at least one criterion is given (code/name,
    member, fund, type, GL head, role); then the matching accounts, by code,
    paginated. Static facets (account types, GL heads) always ride along so the
    form can populate its selects without a query."""
    permission_classes = [RequireCapability("ledger.view")]

    def get(self, request):
        p = request.query_params
        facets = {
            "types": [{"value": v, "label": l} for v, l in Account.Type.choices],
            "gl_heads": [{"value": v, "label": l} for v, l in _FUND_GL.items()],
            "roles": [{"value": "gl", "label": "GL head"},
                      {"value": "pool", "label": "Pool control"},
                      {"value": "member", "label": "Member sub-ledger"}],
        }

        # Inquiry-first: no criteria → no results, just a prompt (+ static facets).
        if not _has_criteria(p):
            return Response({"results": [], "count": 0, "has_more": False,
                             "prompt": True, "facets": facets})

        qs = filter_accounts(p)
        try:
            limit = min(max(int(p.get("limit", 50)), 1), 100)
            offset = max(int(p.get("offset", 0)), 0)
        except (TypeError, ValueError):
            limit, offset = 50, 0
        total = qs.count()

        return Response({
            "results": [_row(a) for a in qs[offset:offset + limit]],
            "count": total, "has_more": offset + limit < total,
            "prompt": False, "facets": facets,
        })


class Account360View(OpsAPIView):
    """GET /api/ops/accounts/<id>/ — one account in full: its identity (id,
    account_uid, code), where it sits in the tree (parent + immediate children),
    and its balance. The detail companion to the browser."""
    permission_classes = [RequireCapability("ledger.view")]

    def get(self, request, account_id):
        acct = get_object_or_404(
            Account.objects.select_related("parent", "owner"), pk=account_id)
        payload = _row(acct)
        payload["parent"] = _row(acct.parent) if acct.parent_id else None
        # Immediate children (a GL head's pools, or a pool's members) — capped.
        children = (Account.objects.select_related("parent", "owner")
                    .filter(parent=acct).order_by("code")[:100])
        payload["children"] = [_row(c) for c in children]
        payload["child_count"] = Account.objects.filter(parent=acct).count()
        return Response(payload)
