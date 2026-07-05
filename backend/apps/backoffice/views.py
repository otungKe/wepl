"""Back Office API (/api/ops/) — P0 spine."""
from __future__ import annotations

from rest_framework.response import Response
from rest_framework.views import APIView

from .audit import record_action
from .capabilities import capabilities_for, roles_for
from .permissions import IsOperator, RequireCapability
from .search import federated_search


class OpsMeView(APIView):
    """GET /api/ops/me/ — the operator's identity, roles and capabilities.

    Drives the console: the web shell renders navigation and actions purely from
    the returned ``capabilities`` (authoritative gating is still server-side on
    each endpoint).
    """
    permission_classes = [IsOperator]

    def get(self, request):
        u = request.user
        return Response({
            "id": u.id,
            "phone_number": u.phone_number,
            "name": getattr(u, "name", "") or "",
            "is_superuser": u.is_superuser,
            "roles": roles_for(u),
            "capabilities": sorted(capabilities_for(u)),
        })


class OpsPingView(APIView):
    """GET /api/ops/ping/ — cheap authenticated liveness for the console shell."""
    permission_classes = [IsOperator]

    def get(self, request):
        return Response({"ok": True})


class OpsSearchView(APIView):
    """GET /api/ops/search/?q= — federated, capability-scoped operator search
    powering the ⌘K command palette. Each result type is only searched if the
    operator holds its capability. Non-trivial searches are audited (who looked
    up what) for the compliance trail."""
    permission_classes = [RequireCapability("search.global")]

    def get(self, request):
        q = request.query_params.get("q", "")
        payload = federated_search(request.user, q)
        if len(payload["query"]) >= 3 and payload["results"]:
            record_action(
                action="ops.search.performed", request=request,
                metadata={"query": payload["query"], "counts": payload["counts"]},
            )
        return Response(payload)
