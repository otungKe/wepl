"""
Payment operations service — the FinOps desk's levers (OP-1).

When a rail webhook is lost or a payout stalls, a member's money sits in limbo.
This service lets an operator (not a developer) heal it, going through the *same*
machinery a received callback would, so there is exactly one code path to money
truth. No lever hand-rolls a journal or mutates state directly:

- ``requery``    — ask the rail for truth via the provider port and apply the
  result identically to a callback (finalise on success; fail + reverse the
  reserved-funds journal on failure). Idempotent under the state-machine's
  optimistic lock, so a lost webhook heals the same whether it later arrives.
- ``mark_failed`` — terminally fail a stuck payout the rail confirms never
  completed. Requires a fresh query that is *not* success — operator opinion is
  not enough to strand or unstick money.

Scope (increment 1): the payout rail (B2C ``FinancialTransaction``s stuck in
PENDING/PROCESSING) — where "money in limbo" actually bites. Pay-ins are
``MpesaSTKRequest`` rows already auto-requeried by ``poll_mpesa_stk_status``;
arbitrary reversal of a settled payout is deferred to OP-3 maker-checker; payout
re-submission (retry) is a later increment.
"""
from __future__ import annotations

import logging

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.core.exceptions import TransitionError
from apps.ledger.models import FinancialTransaction as FT

logger = logging.getLogger(__name__)

# Op types that send money *out* — the ones that can strand a member's payout.
PAYOUT_OP_TYPES: frozenset[str] = frozenset({
    FT.OpType.DISBURSEMENT,
    FT.OpType.STANDING_ORDER,
    FT.OpType.ROSCA_PAYOUT,
    FT.OpType.ADVANCE_DISBURSEMENT,
    FT.OpType.WELFARE_CLAIM,
})

# States a stuck payout can be healed from.
_OPEN_STATES = (FT.State.PENDING, FT.State.PROCESSING)


class PaymentOpsService:
    """Operator-facing recovery levers over stuck payout FinancialTransactions."""

    # ── Public levers ─────────────────────────────────────────────────────────
    @classmethod
    def requery(cls, ft: FT, *, actor_label: str = "") -> dict:
        """Ask the rail for the payout's true state and apply it. Safe to call
        repeatedly — already-terminal movements are a no-op."""
        cls._guard_payout(ft)
        if ft.state not in _OPEN_STATES:
            return cls._result("noop", ft, "Movement is already terminal.")
        if not ft.mpesa_conversation_id:
            return cls._result("unknown", ft, "No rail reference to query yet.")

        state = cls._query_state(ft.mpesa_conversation_id)
        if state == "success":
            return cls._apply_success(ft, actor_label=actor_label)
        if state == "failed":
            return cls._apply_failure(
                ft, reason="Rail reports the payout failed.", actor_label=actor_label)
        return cls._result("pending", ft, "Rail still reports the payout pending.")

    @classmethod
    def retry_payout(cls, ft: FT, *, actor_label: str = "") -> dict:
        """Re-dispatch a payout that stalled before ever reaching the rail (stuck
        PENDING/PROCESSING with no rail reference). Re-drives the canonical B2C
        door (``execute_b2c_payout``), whose own guards prevent a double-send.

        Not for: a settled payout (nothing to do), a failed one (its funds were
        already restored — re-issuing is a fresh disbursement, not a re-send), or
        one already dispatched (use ``requery`` to fetch its result)."""
        cls._guard_payout(ft)
        if ft.state == FT.State.SUCCESS:
            raise ValidationError("This payout already succeeded.")
        if ft.state == FT.State.FAILED:
            raise ValidationError(
                "A failed payout can't be re-sent — its funds were restored. "
                "Re-initiate the disbursement from the source flow.")
        if ft.mpesa_conversation_id:
            raise ValidationError(
                "This payout was already dispatched to the rail — use Requery to fetch its result.")

        from apps.ledger.tasks import execute_b2c_payout
        # Synchronous: run the canonical door in-process so the operator sees the
        # outcome now. It is idempotent — the conversation-id guard blocks any
        # double-send if a callback lands mid-flight.
        execute_b2c_payout.apply(args=[ft.id])
        ft.refresh_from_db()
        if ft.mpesa_conversation_id:
            logger.info("FinOps: payout FT %s re-dispatched by %s", ft.id, actor_label or "ops")
            return cls._result("resent", ft, "Re-dispatched to the rail; awaiting confirmation.")
        if ft.state == FT.State.FAILED:
            return cls._result("failed", ft, ft.failure_reason or "Re-dispatch failed.")
        return cls._result("attempted", ft, "Re-dispatch attempted; no rail reference yet.")

    @classmethod
    @transaction.atomic
    def reverse(cls, ft: FT, *, reason: str, actor_label: str = "") -> dict:
        """Reverse a *settled* movement: post the exact inverse journal and move
        SUCCESS → REVERSED. Destructive and irreversible, so it is only reachable
        through maker-checker (OP-3) — never a single operator. Idempotent: the
        reversal journal keys off the original."""
        reason = (reason or "").strip()
        if not reason:
            raise ValidationError("A reason is required to reverse a movement.")
        if ft.state != FT.State.SUCCESS:
            raise ValidationError("Only a settled (SUCCESS) movement can be reversed.")

        from apps.ledger.posting import reverse_financial_transaction
        entry = reverse_financial_transaction(ft, note=reason)
        try:
            ft.transition_to(FT.State.REVERSED, failure_reason=reason)
        except TransitionError:
            ft.refresh_from_db()
            return cls._result("noop", ft, "Already reversed by a concurrent update.")
        logger.warning("FinOps: FT %s REVERSED by %s — %s", ft.id, actor_label or "ops", reason)
        return cls._result(
            "reversed", ft,
            f"Reversed via JE-{entry.id}." if entry else "Reversed (no journal to invert).")

    @classmethod
    def mark_failed(cls, ft: FT, *, reason: str, actor_label: str = "") -> dict:
        """Terminally fail a stuck payout the rail confirms never completed. If a
        fresh query instead shows success, it is healed as success (never
        stranded). A reason is mandatory."""
        cls._guard_payout(ft)
        reason = (reason or "").strip()
        if not reason:
            raise ValidationError("A reason is required to fail a movement.")
        if ft.state not in _OPEN_STATES:
            raise ValidationError("Only a pending or processing movement can be failed.")

        if ft.mpesa_conversation_id:
            if cls._query_state(ft.mpesa_conversation_id) == "success":
                # The rail says it actually went through — heal, don't strand.
                return cls._apply_success(ft, actor_label=actor_label)
        return cls._apply_failure(ft, reason=reason, actor_label=actor_label)

    # ── Internals ─────────────────────────────────────────────────────────────
    @staticmethod
    def _guard_payout(ft: FT) -> None:
        if ft.op_type not in PAYOUT_OP_TYPES:
            raise ValidationError(
                "This lever handles payout movements only; pay-ins are recovered "
                "on their own rail.")

    @staticmethod
    def _query_state(provider_ref: str) -> str:
        from apps.payments.providers.registry import get_provider
        try:
            return get_provider().query_status(provider_ref=provider_ref).state
        except Exception:
            logger.exception("requery: rail status query failed for %s", provider_ref)
            return "unknown"

    @classmethod
    @transaction.atomic
    def _apply_success(cls, ft: FT, *, actor_label: str = "") -> dict:
        """Finalise a confirmed payout exactly as the B2C callback would. The rail
        status query carries no receipt, so it finalises without one."""
        from apps.mpesa.views import _on_b2c_success
        try:
            ft.transition_to(FT.State.SUCCESS)
        except TransitionError:
            ft.refresh_from_db()
            return cls._result("noop", ft, "Already resolved by a concurrent update.")
        _on_b2c_success(ft, "")
        logger.info("FinOps: payout FT %s healed to SUCCESS by %s", ft.id, actor_label or "ops")
        return cls._result("healed_success", ft, "Payout confirmed and finalised.")

    @classmethod
    @transaction.atomic
    def _apply_failure(cls, ft: FT, *, reason: str, actor_label: str = "") -> dict:
        """Fail the payout and restore reserved funds via the reversal path the
        B2C failure callback uses."""
        from apps.ledger.posting import reverse_financial_transaction
        from apps.ledger.tasks import _update_context_on_failure
        try:
            ft.transition_to(FT.State.FAILED, failure_reason=reason)
        except TransitionError:
            ft.refresh_from_db()
            return cls._result("noop", ft, "Already resolved by a concurrent update.")
        reverse_financial_transaction(ft, note=reason)   # idempotent; no-op if nothing posted
        _update_context_on_failure(ft)
        logger.warning("FinOps: payout FT %s failed by %s — %s", ft.id, actor_label or "ops", reason)
        return cls._result("healed_failed", ft, reason)

    @staticmethod
    def _result(outcome: str, ft: FT, detail: str) -> dict:
        return {"outcome": outcome, "state": ft.state, "detail": detail}
