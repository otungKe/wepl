"""Permission-filtered, ranked search (ADR-0017).

v1 uses Postgres full-text search (SearchVector/SearchRank, no extension needed)
for the long-text entities and a name/phone match for users. The defining
property is **permission filtering at query time** — every base queryset is
constrained to rows the actor may see, so search can never leak a private
community, a closed contribution, or a non-discoverable user. Tenant scope is
applied when the request is pinned to a tenant.

An OpenSearch/Meilisearch backend and stored tsvector + GIN indexes are the
documented v2; this service is the seam callers use either way.
"""
from django.contrib.auth import get_user_model
from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db.models import Q

User = get_user_model()
DEFAULT_LIMIT = 20
MAX_LIMIT = 50
TYPES = ('communities', 'contributions', 'users')


def _fts(qs, query, weighted_fields, limit):
    vector = None
    for field, weight in weighted_fields:
        v = SearchVector(field, weight=weight)
        vector = v if vector is None else vector + v
    sq = SearchQuery(query)
    return list(
        qs.annotate(rank=SearchRank(vector, sq))
          .filter(rank__gt=0)
          .order_by('-rank')
          .distinct()[:limit]
    )


class SearchService:

    @staticmethod
    def search(actor, q, *, types=None, limit=DEFAULT_LIMIT):
        q = (q or '').strip()
        types = tuple(types) if types else TYPES
        limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
        out = {}
        if not q:
            return {t: [] for t in types}
        if 'communities' in types:
            out['communities'] = SearchService._communities(actor, q, limit)
        if 'contributions' in types:
            out['contributions'] = SearchService._contributions(actor, q, limit)
        if 'users' in types:
            out['users'] = SearchService._users(actor, q, limit)
        return out

    # ── per-type, permission-filtered ────────────────────────────────────────
    @staticmethod
    def _tenant_id():
        from apps.tenants.rls import current_tenant_id
        return current_tenant_id()

    @staticmethod
    def _communities(actor, q, limit):
        from apps.communities.models import Community
        qs = Community.objects.filter(
            Q(is_private=False) | Q(memberships__user=actor, memberships__is_active=True)
        )
        tid = SearchService._tenant_id()
        if tid is not None:
            qs = qs.filter(tenant_id=tid)
        rows = _fts(qs, q, [('name', 'A'), ('description', 'B'), ('location', 'C')], limit)
        return [
            {'id': c.id, 'type': 'community', 'name': c.name,
             'description': (c.description or '')[:160], 'is_private': c.is_private}
            for c in rows
        ]

    @staticmethod
    def _contributions(actor, q, limit):
        from apps.contributions.models import Contribution
        qs = Contribution.objects.filter(is_active=True).filter(
            Q(visibility='open')
            | Q(participants__user=actor, participants__is_active=True)
            | Q(community__memberships__user=actor, community__memberships__is_active=True)
        )
        tid = SearchService._tenant_id()
        if tid is not None:
            qs = qs.filter(community__tenant_id=tid)
        rows = _fts(qs, q, [('title', 'A'), ('description', 'B')], limit)
        return [
            {'id': c.id, 'type': 'contribution', 'title': c.title,
             'description': (c.description or '')[:160], 'visibility': c.visibility}
            for c in rows
        ]

    @staticmethod
    def _users(actor, q, limit):
        # Only discoverable users (privacy_prefs.discoverable, default True when no row).
        qs = (
            User.objects.filter(is_active=True)
            .filter(Q(privacy_prefs__discoverable=True) | Q(privacy_prefs__isnull=True))
            .filter(Q(name__icontains=q) | Q(phone_number=q))
            .distinct()[:limit]
        )
        return [
            {'id': u.id, 'type': 'user', 'name': u.name or '',
             'phone_number': u.phone_number}
            for u in qs
        ]
