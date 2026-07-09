"""
Maker-checker (dual control) for the Back Office — OP-3 Part 2.

A *flagged* action never executes for the operator who invokes it. Instead
``require_approval`` records an ``OpsApprovalRequest``; a second operator
(never the requester) ``decide``s it, and only on approval does the original
domain-service call run — attributed to both identities. This is the identity
analogue of the ledger's "one door": destructive ops actions have exactly one
path to execution, and it is two-person.

Adding a flagged action = register an executor here (its capability to *request*,
how to run it, and a human summary). The generic checker capability is
``approvals.decide``; who may *request* is the action's own capability.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Callable

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .capabilities import has_capability
from .models import OpsApprovalRequest

logger = logging.getLogger(__name__)

APPROVAL_TTL = timedelta(hours=24)
CHECKER_CAPABILITY = "approvals.decide"


@dataclass(frozen=True)
class FlaggedAction:
    capability: str                       # capability required to *request* it
    execute: Callable[..., dict]          # (params, *, actor_label) -> result dict
    summary: Callable[[dict], str]        # (params) -> one-line description
    target_type: str = ""


_REGISTRY: dict[str, FlaggedAction] = {}


def register(action: str, spec: FlaggedAction) -> None:
    _REGISTRY[action] = spec


def is_flagged(action: str) -> bool:
    return action in _REGISTRY


def spec_for(action: str) -> FlaggedAction:
    try:
        return _REGISTRY[action]
    except KeyError:
        raise ValidationError(f"Unknown flagged action: {action!r}.")


# ── Maker side ────────────────────────────────────────────────────────────────
def require_approval(action: str, *, params: dict, actor, reason: str,
                     target_id: str = "") -> OpsApprovalRequest:
    """Record a pending request for a flagged action. Raises if the actor may not
    request this action or the reason is missing."""
    spec = spec_for(action)
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("A reason is required to request this action.")
    if not has_capability(actor, spec.capability):
        raise ValidationError("You do not hold the capability to request this action.")

    return OpsApprovalRequest.objects.create(
        action=action,
        params=params,
        reason=reason,
        summary=spec.summary(params),
        target_type=spec.target_type,
        target_id=str(target_id),
        requested_by=actor,
        expires_at=timezone.now() + APPROVAL_TTL,
    )


# ── Checker side ──────────────────────────────────────────────────────────────
def decide(request_id: int, *, checker, approve: bool, note: str = "") -> OpsApprovalRequest:
    """Approve (→ execute) or reject a pending request. Enforces: checker holds
    ``approvals.decide``, checker ≠ requester (no self-approval), the request is
    still PENDING and unexpired, and a request cannot execute twice."""
    if not has_capability(checker, CHECKER_CAPABILITY):
        raise ValidationError("You do not hold the capability to decide approvals.")

    with transaction.atomic():
        # Lock the row so two checkers cannot both execute it.
        appr = (OpsApprovalRequest.objects
                .select_for_update()
                .get(pk=request_id))

        if appr.status != OpsApprovalRequest.Status.PENDING:
            raise ValidationError(f"This request is already {appr.get_status_display().lower()}.")
        if appr.is_expired:
            appr.status = OpsApprovalRequest.Status.EXPIRED
            appr.save(update_fields=["status"])
            raise ValidationError("This request has expired; ask the requester to raise a new one.")
        if appr.requested_by_id == checker.id:
            raise ValidationError("You cannot approve your own request — a second operator must decide.")

        appr.decided_by = checker
        appr.decided_at = timezone.now()
        appr.decision_note = (note or "").strip()

        if not approve:
            appr.status = OpsApprovalRequest.Status.REJECTED
            appr.save(update_fields=["decided_by", "decided_at", "decision_note", "status"])
            logger.info("Approval #%s REJECTED by %s", appr.pk, checker.email)
            return appr

        spec = spec_for(appr.action)
        attribution = f"maker:{appr.requested_by.email};checker:{checker.email}"
        try:
            result = spec.execute(appr.params, actor_label=attribution)
        except Exception as exc:
            appr.status = OpsApprovalRequest.Status.FAILED
            appr.result = {"error": str(exc)}
            appr.save(update_fields=["decided_by", "decided_at", "decision_note", "status", "result"])
            logger.exception("Approval #%s execution FAILED", appr.pk)
            raise ValidationError(f"Approved, but execution failed: {exc}")

        appr.status = OpsApprovalRequest.Status.APPROVED
        appr.result = result if isinstance(result, dict) else {"result": str(result)}
        appr.save(update_fields=["decided_by", "decided_at", "decision_note", "status", "result"])
        logger.info("Approval #%s APPROVED+EXECUTED (%s)", appr.pk, attribution)
        return appr
