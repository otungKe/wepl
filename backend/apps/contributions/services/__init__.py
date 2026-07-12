"""Contribution services (ADR-0013 module split).

``services.py`` (1,919 lines) became this package — one module per sub-domain —
without changing the public import surface: ``from apps.contributions.services
import ContributionService`` (and ``_notify``) still work, because every name is
re-exported here.
"""
from ._common import _dn, _notify, _compute_next_run  # public helper surface
from .contribution import ContributionService
from .rosca import ROSCAService
from .disbursement import DisbursementService
from .welfare import WelfareService
from .advances import EmergencyAdvanceService
from .standing_orders import StandingOrderService
from .amendments import AmendmentService
from .join_requests import ContributionJoinRequestService
from .shares import SharesService

__all__ = [
    "ContributionService", "ROSCAService", "DisbursementService",
    "WelfareService", "EmergencyAdvanceService", "StandingOrderService",
    "AmendmentService", "ContributionJoinRequestService", "SharesService",
    "_notify", "_dn", "_compute_next_run",
]
