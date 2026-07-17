"""
Contribution business logic.

Key architectural principles enforced here:
  - M-Pesa HTTP calls are NEVER made inside @transaction.atomic blocks.
    They are dispatched to Celery tasks via transaction.on_commit().
  - All money movement goes through the double-entry ledger via post_journal()
    (apps.ledger). Balances are derived from immutable journal lines — there are
    no mutable balance columns.
  - Idempotency keys are used for every financial operation.
  - Authorization uses FinancialPermissions — one implementation, not six.
"""
import logging
import math
import random
from datetime import timedelta
from decimal import Decimal

logger = logging.getLogger(__name__)

from django.db import transaction
from django.db.models import F
from django.core.exceptions import ValidationError, PermissionDenied

from apps.audit.services import AuditService
from apps.core.policy import require
from django.utils import timezone

from ..models import (
    Contribution, ContributionParticipant,
    SharesFund, ShareHolding,
    ROSCASlot, DisbursementRequest, DisbursementVote,
    WelfareFund, WelfareContribution, WelfareClaim, WelfareVote,
    EmergencyAdvance,
    StandingOrder, StandingOrderSlot,
    ContributionAmendment, ContributionAmendmentVote,
    ContributionJoinRequest,
)
from apps.activity.models import Activity
from apps.activity.services import ActivityService
from apps.users.tiers import AccessPolicy
from apps.ledger.permissions import FinancialPermissions
from apps.ledger.writer import create_fin_transaction
from apps.ledger.models import FinancialTransaction, JournalEntry
# P0-05 strangler: post double-entry journals alongside the legacy writes. The
# ledger becomes a parallel source of truth now; reads/gates flip to it in P0-06
# and the legacy writes are deleted in P0-07.
from apps.ledger.posting import post_journal
from apps.ledger import posting_map as _pm
from apps.ledger.money import Money
# P0-06: read pool/member balances from the ledger (the authoritative source).
from apps.ledger.balances import fund_balance, account_balance
from apps.ledger import coa as _coa


def _dn(user) -> str:
    """Return the user's display name, falling back to their phone number."""
    return (user.name or "").strip() or user.phone_number


# ---------------------------------------------------------------------------
# Async notification helper (routes through the domain event bus)
# ---------------------------------------------------------------------------

from apps.core.events import emit as _emit_event


def _notify(user, notification_type, title, message, **kwargs):
    """
    Emit a domain event that the notifications app will turn into a
    Notification record (via Celery, after the current transaction commits).

    services.py no longer imports from apps.notifications — the coupling
    is inverted: apps.notifications.receivers listens to apps.core.events.
    """
    user_id = user.id if hasattr(user, 'id') else int(user)
    _emit_event(notification_type, user_id=user_id, title=title, message=message, **kwargs)


# ---------------------------------------------------------------------------
# Standing-order schedule helper
# ---------------------------------------------------------------------------

def _compute_next_run(frequency: str, from_dt) -> object:
    """Return the next execution datetime for a standing order."""
    if frequency == 'daily':
        return from_dt + timedelta(days=1)
    if frequency == 'weekly':
        return from_dt + timedelta(weeks=1)
    # monthly — approximate as 30 days; good enough for scheduling
    return from_dt + timedelta(days=30)


# ---------------------------------------------------------------------------
# Core contribution lifecycle
# ---------------------------------------------------------------------------

__all__ = [
    # stdlib / django
    "logging", "math", "random", "timedelta", "Decimal",
    "transaction", "F", "ValidationError", "PermissionDenied", "timezone",
    # cross-cutting services / helpers
    "AuditService", "require", "ActivityService", "Activity", "AccessPolicy", "FinancialPermissions",
    "logger", "_dn", "_notify", "_emit_event", "_compute_next_run",
    # models
    "Contribution", "ContributionParticipant",
    "SharesFund", "ShareHolding", "ROSCASlot", "DisbursementRequest",
    "DisbursementVote", "WelfareFund", "WelfareContribution", "WelfareClaim",
    "WelfareVote", "EmergencyAdvance", "StandingOrder", "StandingOrderSlot",
    "ContributionAmendment", "ContributionAmendmentVote", "ContributionJoinRequest",
    # ledger
    "create_fin_transaction", "FinancialTransaction", "JournalEntry",
    "post_journal", "_pm", "Money", "fund_balance", "account_balance", "_coa",
]
