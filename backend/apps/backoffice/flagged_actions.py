"""
Registry of maker-checked (flagged) ops actions — OP-3 Part 2.

Each flagged action declares the capability required to *request* it, how to
execute it once approved, and a human summary for the approvals inbox. Registered
from ``BackofficeConfig.ready()``. The first flagged action is a money reversal
(OP-1's deferred destructive lever); LimitRule changes, control-override
issuance, and staff role changes plug in here the same way.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError

from .approvals import FlaggedAction, register

ACTION_REVERSAL = "finops.reverse"
ACTION_PHONE_CHANGE = "users.change_phone"
ACTION_RECOVER_OWNERSHIP = "communities.recover_ownership"


def _execute_reversal(params: dict, *, actor_label: str = "") -> dict:
    from apps.ledger.models import FinancialTransaction
    from apps.payments.ops import PaymentOpsService
    try:
        ft = FinancialTransaction.objects.get(pk=params["ft_id"])
    except FinancialTransaction.DoesNotExist:
        raise ValidationError("The movement to reverse no longer exists.")
    return PaymentOpsService.reverse(ft, reason=params.get("reason", ""), actor_label=actor_label)


def _summary_reversal(params: dict) -> str:
    return f"Reverse movement #{params.get('ft_id')} — KES {params.get('amount', '?')}"


def _execute_phone_change(params: dict, *, actor_label: str = "") -> dict:
    """Swap the member's login/payout phone number and kill every session.
    The number was validated + uniqueness-checked at request time; both are
    re-checked here because approval may land much later."""
    import re
    from django.contrib.auth import get_user_model
    from apps.users import sessions as session_svc

    User = get_user_model()
    try:
        u = User.objects.get(pk=params["user_id"], is_staff=False)
    except User.DoesNotExist:
        raise ValidationError("The member no longer exists.")

    new_phone = (params.get("new_phone") or "").strip()
    if not re.fullmatch(r"\+?254(7|1)\d{8}", new_phone):
        raise ValidationError("The requested phone number is not valid.")
    if User.objects.filter(phone_number=new_phone).exclude(pk=u.pk).exists():
        raise ValidationError("That phone number now belongs to another account.")
    if u.phone_number != params.get("old_phone"):
        raise ValidationError(
            "The member's phone changed since this request was raised — re-verify and re-request.")

    old = u.phone_number
    u.phone_number = new_phone
    u.save(update_fields=["phone_number"])
    revoked = session_svc.revoke_all_for_user(u)

    # Domain-level audit event targeting the MEMBER (the decide-time record
    # targets the approval request) so the change shows in the user's 360 trail.
    # Best-effort — auditing must never unwind an executed approval.
    try:
        from apps.audit.models import AuditEvent
        AuditEvent.objects.create(
            action="user.phone_changed", actor=None, actor_label=actor_label[:120],
            target_type="user", target_id=str(u.pk),
            metadata={"before": old, "after": new_phone, "sessions_revoked": revoked})
    except Exception:  # pragma: no cover - telemetry only
        pass
    return {"user_id": u.pk, "old_phone": old, "new_phone": new_phone,
            "sessions_revoked": revoked}


def _summary_phone_change(params: dict) -> str:
    return (f"Change member #{params.get('user_id')} phone "
            f"{params.get('old_phone', '?')} → {params.get('new_phone', '?')}")


def _execute_recover_ownership(params: dict, *, actor_label: str = "") -> dict:
    """Hand an orphaned community to one of its active members. The member and
    the community are re-checked here because approval may land much later."""
    from apps.communities.models import Community
    from apps.communities.services import CommunityService
    try:
        community = Community.objects.get(pk=params["community_id"])
    except Community.DoesNotExist:
        raise ValidationError("The community no longer exists.")
    if community.created_by_id != params.get("old_owner_id"):
        raise ValidationError(
            "The community's owner changed since this request was raised — re-check and re-request.")
    CommunityService.recover_ownership(
        community, params["membership_id"], reason=params.get("reason", ""),
        operator_label=actor_label)
    community.refresh_from_db()
    return {"community_id": community.pk, "old_owner_id": params.get("old_owner_id"),
            "new_owner_id": community.created_by_id}


def _summary_recover_ownership(params: dict) -> str:
    return (f"Recover community #{params.get('community_id')}: hand ownership to "
            f"membership #{params.get('membership_id')}")


def register_all() -> None:
    register(ACTION_REVERSAL, FlaggedAction(
        capability="finops.reverse",
        execute=_execute_reversal,
        summary=_summary_reversal,
        target_type="financial_transaction",
    ))
    register(ACTION_PHONE_CHANGE, FlaggedAction(
        capability="users.manage",
        execute=_execute_phone_change,
        summary=_summary_phone_change,
        target_type="user",
    ))
    register(ACTION_RECOVER_OWNERSHIP, FlaggedAction(
        capability="communities.manage",
        execute=_execute_recover_ownership,
        summary=_summary_recover_ownership,
        target_type="community",
    ))
