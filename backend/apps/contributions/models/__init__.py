"""Contribution domain models, one module per bounded context (ADR-0013).

Split out of a single 943-line ``models.py``; the modules mirror
``apps/contributions/services/`` name for name. Every model is re-exported here,
so ``from apps.contributions.models import X`` resolves exactly as before and no
call site changed. The app label is untouched, so no migration is involved.
"""
from .contribution import Contribution, ContributionParticipant
from .shares import SharesFund, ShareHolding
from .rosca import ROSCASlot
from .standing_orders import StandingOrder, StandingOrderSlot
from .disbursement import DisbursementRequest, DisbursementVote
from .welfare import WelfareFund, WelfareContribution, WelfareClaim, WelfareVote
from .advances import EmergencyAdvance
from .amendments import ContributionAmendment, ContributionAmendmentVote
from .join_requests import ContributionJoinRequest
from .pool_governance import PoolActionRequest, PoolActionApproval

# 0001_initial serialises this callable by its dotted path, so it must stay
# importable as apps.contributions.models._generate_invite_code.
from .contribution import _generate_invite_code

__all__ = [
    "Contribution",
    "ContributionParticipant",
    "SharesFund",
    "ShareHolding",
    "ROSCASlot",
    "StandingOrder",
    "StandingOrderSlot",
    "DisbursementRequest",
    "DisbursementVote",
    "WelfareFund",
    "WelfareContribution",
    "WelfareClaim",
    "WelfareVote",
    "EmergencyAdvance",
    "ContributionAmendment",
    "ContributionAmendmentVote",
    "ContributionJoinRequest",
    "PoolActionRequest",
    "PoolActionApproval",
    "_generate_invite_code",
]
