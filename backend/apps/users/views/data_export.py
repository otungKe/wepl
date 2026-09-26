from ._common import *  # shared imports/helpers (ADR-0013 view split)
from ..lifecycle import export_account


class DataExportView(APIView):
    """GET /api/users/data-export/ — compile everything WEPL holds about the
    requesting user into one JSON document (self-serve data-rights export).

    Scoped strictly to request.user. Each context contributes its own sections
    through ``apps.core.lifecycle``; ``apps.users.lifecycle.export_account``
    assembles them."""
    permission_classes = [IsActiveSession]

    def get(self, request):
        return Response(export_account(request.user))
