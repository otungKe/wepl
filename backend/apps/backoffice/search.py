"""
Federated operator search (P0.2).

One query hits every entity an operator is allowed to see and returns typed,
deep-linkable results for the ⌘K command palette. Each searcher is capability-
gated, isolated (a failing searcher never breaks the palette) and bounded (small
per-type limit) so it scales to large tables.

A result is a flat dict the console can render and navigate:
    {type, id, label, sublabel, url}
where ``url`` is the console deep-link (the web app owns the /admin route map).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from .capabilities import has_capability

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Searcher:
    type: str
    capability: str
    run: Callable[[str, int], list[dict]]


# ── Per-entity searchers ─────────────────────────────────────────────────────
def _users(q: str, limit: int) -> list[dict]:
    from django.db.models import Q
    from apps.users.models import User
    qs = (User.objects
          .filter(Q(phone_number__icontains=q) | Q(name__icontains=q))
          .order_by("-date_joined")[:limit])
    return [{
        "type": "user", "id": u.id,
        "label": u.name or u.phone_number,
        "sublabel": u.phone_number,
        "url": f"/admin/users/{u.id}",
    } for u in qs]


def _communities(q: str, limit: int) -> list[dict]:
    from apps.communities.models import Community
    qs = Community.objects.filter(name__icontains=q).order_by("-created_at")[:limit]
    return [{
        "type": "community", "id": c.id,
        "label": c.name,
        "sublabel": f"community · {c.category or 'general'}",
        "url": f"/admin/communities/{c.id}",
    } for c in qs]


def _verification(q: str, limit: int) -> list[dict]:
    from django.db.models import Q
    from apps.users.models import KYCProfile
    qs = (KYCProfile.objects
          .filter(Q(id_number__icontains=q) | Q(user__phone_number__icontains=q)
                  | Q(given_names__icontains=q) | Q(surname__icontains=q))
          .select_related("user").order_by("-submitted_at")[:limit])
    return [{
        "type": "verification", "id": k.user_id,
        "label": k.full_name or k.user.phone_number,
        "sublabel": f"KYC {k.status} · ID {k.id_number}",
        "url": f"/admin/verification/{k.user_id}",
    } for k in qs]


def _journals(q: str, limit: int) -> list[dict]:
    from django.db.models import Q
    from apps.ledger.models import JournalEntry
    cond = Q(idempotency_key__icontains=q) | Q(op_type__icontains=q)
    if q.isdigit():
        cond |= Q(id=int(q))
    qs = JournalEntry.objects.filter(cond).order_by("-id")[:limit]
    return [{
        "type": "journal", "id": j.id,
        "label": f"#{j.id} · {j.op_type}",
        "sublabel": (j.narration or j.idempotency_key)[:60],
        "url": f"/admin/ledger/journals/{j.id}",
    } for j in qs]


SEARCHERS: list[Searcher] = [
    Searcher("user",         "users.view",         _users),
    Searcher("verification", "verification.view",  _verification),
    Searcher("community",    "communities.view",   _communities),
    Searcher("journal",      "ledger.view",        _journals),
]


def federated_search(user, q: str, *, limit_per_type: int = 6) -> dict:
    """Run every searcher the ``user`` is permitted to use. Returns
    ``{"query": q, "results": [...], "counts": {type: n}}``."""
    q = (q or "").strip()
    results: list[dict] = []
    counts: dict[str, int] = {}
    if len(q) < 2:
        return {"query": q, "results": results, "counts": counts}

    for s in SEARCHERS:
        if not has_capability(user, s.capability):
            continue
        try:
            rows = s.run(q, limit_per_type)
        except Exception:
            logger.exception("ops search: searcher %s failed for q=%r", s.type, q)
            continue
        counts[s.type] = len(rows)
        results.extend(rows)
    return {"query": q, "results": results, "counts": counts}
