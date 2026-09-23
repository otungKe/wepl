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
- ``confirm_paid`` — settle a stuck payout the operator has found paid on the
  rail's own records, carrying that receipt. The counterpart the stale sweep
  relies on: it leaves a payout of unknown outcome in PROCESSING rather than
  reverse it, and on M-Pesa every stuck payout's outcome is unknown.

Rail queries here are *payout* queries (``request_payout_result``), never the
collection poll ``query_status``: on M-Pesa that is an STK query, which cannot
describe a B2C payout. M-Pesa's payout query answers asynchronously, so it
reports ``unknown`` and the desk decides from the M-Pesa portal.

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
from apps.payments.money_activity import rail_for

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
        provider_ref = rail_for(ft).conversation_id
        if not provider_ref:
            return cls._result("unknown", ft, "No rail reference to query yet.")

        state = cls._query_state(provider_ref)
        if state == "success":
            return cls._apply_success(ft, actor_label=actor_label)
        if state == "failed":
            return cls._apply_failure(
                ft, reason="Rail reports the payout failed.", actor_label=actor_label)
        if state == "pending":
            return cls._result("pending", ft, "Rail still reports the payout pending.")
        return cls._result(
            "unknown", ft,
            "The rail can't confirm this payout's outcome from here. Check its own "
            "records (the M-Pesa portal), then confirm it paid or mark it failed.")

    @classmethod
    def retry_payout(cls, ft: FT, *, actor_label: str = "") -> dict:
        """Re-dispatch a payout that stalled before ever reaching the rail (stuck
        PENDING/PROCESSING with no rail reference). Re-drives the canonical B2C
        door (``execute_payout``), whose own guards prevent a double-send.

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
        if rail_for(ft).conversation_id:
            raise ValidationError(
                "This payout was already dispatched to the rail — use Requery to fetch its result.")

        from apps.payments.payouts import execute_payout
        # Synchronous: run the canonical door in-process so the operator sees the
        # outcome now. It is idempotent — the conversation-id guard blocks any
        # double-send if a callback lands mid-flight.
        execute_payout.apply(args=[ft.id])
        ft.refresh_from_db()
        if rail_for(ft).conversation_id:
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
    def confirm_paid(cls, ft: FT, *, receipt: str, actor_label: str = "") -> dict:
        """Settle a stuck payout the operator has found paid on the rail's own
        records (for M-Pesa, the organisation portal), with its receipt.

        Settling posts no money: the payout's journal was posted when the funds
        were reserved, so this only confirms it and stops it ever being
        reversed. The receipt is mandatory and must not already belong to
        another payment, which catches a mistyped or reused receipt before it
        lands."""
        cls._guard_payout(ft)
        receipt = (receipt or "").strip().upper()
        if not receipt:
            raise ValidationError("The rail's receipt is required to confirm a payout.")
        if ft.state != FT.State.PROCESSING:
            raise ValidationError("Only a payout handed to the rail (PROCESSING) can be confirmed paid.")
        from apps.payments.models import PaymentIntent
        if (PaymentIntent.objects.filter(receipt=receipt)
                .exclude(financial_transaction=ft).exists()):
            raise ValidationError(f"Receipt {receipt} already belongs to another payment.")
        return cls._apply_success(ft, receipt=receipt, actor_label=actor_label)

    @classmethod
    def mark_failed(cls, ft: FT, *, reason: str, actor_label: str = "") -> dict:
        """Terminally fail a stuck payout that never completed, restoring its
        reserved funds. If a fresh query instead shows success, it is healed as
        success (never stranded). A reason is mandatory.

        On M-Pesa the query cannot answer, so this is the operator's word that
        the payout is absent from the M-Pesa portal. Failing a payout that was
        paid pays the member twice; that check is the whole safeguard."""
        cls._guard_payout(ft)
        reason = (reason or "").strip()
        if not reason:
            raise ValidationError("A reason is required to fail a movement.")
        if ft.state not in _OPEN_STATES:
            raise ValidationError("Only a pending or processing movement can be failed.")

        provider_ref = rail_for(ft).conversation_id
        if provider_ref:
            if cls._query_state(provider_ref) == "success":
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
        """The rail's answer for a *payout*: 'success', 'failed', or anything
        else meaning it cannot say (M-Pesa always, since it answers later)."""
        from apps.payments.providers.registry import get_provider
        try:
            return get_provider().request_payout_result(
                provider_ref=provider_ref, remarks="FinOps requery").state
        except Exception:
            logger.exception("requery: rail status query failed for %s", provider_ref)
            return "unknown"

    @staticmethod
    def _settle_intent(ft: FT, *, success: bool, reason: str = "", receipt: str = "") -> None:
        """Settle the linked PaymentIntent through the SAME door a provider callback
        uses (``PaymentService.resolve``), so operator recovery never leaves an
        intent↔FT drift or a privileged shortcut. Best-effort and idempotent — a
        missing or already-terminal intent is a no-op."""
        try:
            from apps.payments.models import PaymentIntent
            from apps.payments.services import PaymentService
            intent = (PaymentIntent.objects
                      .filter(financial_transaction=ft,
                              direction=PaymentIntent.Direction.PAYOUT,
                              status=PaymentIntent.Status.PENDING)
                      .order_by('-created_at')
                      .first())
            if intent is None:
                return
            if intent.provider_ref:
                # The intent's own provider, not whichever one is configured
                # now: the payout was sent on the rail that minted it.
                PaymentService.resolve(
                    provider=intent.provider, provider_ref=intent.provider_ref,
                    success=success, receipt=receipt, failure_message=reason or '')
                return
            # No rail reference: the dispatch died between minting the intent
            # and recording the rail's answer. The intent is still the payout's
            # rail record, so settle it by its link instead of leaving it open.
            intent.transition_to(
                PaymentIntent.Status.SUCCEEDED if success else PaymentIntent.Status.FAILED,
                receipt=receipt, failure_message=reason or '')
        except Exception:
            logger.exception("PaymentOps: intent settlement failed for FT %s", ft.id)

    @classmethod
    @transaction.atomic
    def _apply_success(cls, ft: FT, *, receipt: str = "", actor_label: str = "") -> dict:
        """Finalise a confirmed payout exactly as the B2C callback would. A rail
        status query carries no receipt; an operator's confirmation does."""
        from apps.core.events import emit_event
        try:
            ft.transition_to(FT.State.SUCCESS)
        except TransitionError:
            ft.refresh_from_db()
            return cls._result("noop", ft, "Already resolved by a concurrent update.")
        # Discovery → one durable settlement event (ADR-0028); the inline
        # settlement consumer propagates it (advance domain + notify). Atomic with
        # the transition (this method is @transaction.atomic).
        emit_event(
            'payment.settled',
            aggregate_key=f'ft:{ft.id}',
            dedup_key=f'payment.settled:ft={ft.id}',
            body={'ft_id': ft.id, 'receipt': receipt},
        )
        cls._settle_intent(ft, success=True, receipt=receipt)
        logger.info("FinOps: payout FT %s healed to SUCCESS by %s", ft.id, actor_label or "ops")
        return cls._result("healed_success", ft, "Payout confirmed and finalised.")

    @classmethod
    @transaction.atomic
    def _apply_failure(cls, ft: FT, *, reason: str, actor_label: str = "") -> dict:
        """Fail the payout and restore reserved funds via the reversal path the
        B2C failure callback uses."""
        from apps.core.events import emit_event
        try:
            ft.transition_to(FT.State.FAILED, failure_reason=reason)
        except TransitionError:
            ft.refresh_from_db()
            return cls._result("noop", ft, "Already resolved by a concurrent update.")
        # Discovery → one durable failure event (ADR-0028); the inline settlement
        # consumer restores the reserved funds (ledger reversal) + resets the
        # domain object. Atomic with the transition.
        emit_event(
            'payment.failed',
            aggregate_key=f'ft:{ft.id}',
            dedup_key=f'payment.failed:ft={ft.id}',
            body={'ft_id': ft.id, 'reason': reason},
        )
        cls._settle_intent(ft, success=False, reason=reason)
        logger.warning("FinOps: payout FT %s failed by %s — %s", ft.id, actor_label or "ops", reason)
        return cls._result("healed_failed", ft, reason)

    @staticmethod
    def _result(outcome: str, ft: FT, detail: str) -> dict:
        return {"outcome": outcome, "state": ft.state, "detail": detail}
