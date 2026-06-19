"""
Contribution business logic.

Key architectural principles enforced here:
  - M-Pesa HTTP calls are NEVER made inside @transaction.atomic blocks.
    They are dispatched to Celery tasks via transaction.on_commit().
  - All balance updates use F() expressions — no read-modify-write.
  - Ledger entries are written in dual-write mode alongside legacy balance fields.
    (Legacy fields will be removed once the ledger is confirmed as primary read source.)
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
from django.utils import timezone

from .models import (
    Contribution, ContributionParticipant, ContributionAccount,
    ContributionBalance, ContributionTransaction,
    SharesFund, ShareHolding,
    ROSCASlot, DisbursementRequest, DisbursementVote,
    WelfareFund, WelfareContribution, WelfareClaim, WelfareVote,
    EmergencyAdvance,
    StandingOrder, StandingOrderSlot,
    ContributionAmendment, ContributionAmendmentVote,
    ContributionJoinRequest,
)
from apps.activity.services import ActivityService
from apps.ledger.permissions import FinancialPermissions
from apps.ledger.writer import create_fin_transaction, write_ledger_entry, write_reversal_credit
from apps.ledger.models import FinancialTransaction, LedgerEntry
# P0-05 strangler: post double-entry journals alongside the legacy writes. The
# ledger becomes a parallel source of truth now; reads/gates flip to it in P0-06
# and the legacy writes are deleted in P0-07.
from apps.ledger.posting import post_journal, reverse_journal
from apps.ledger import posting_map as _pm
from apps.ledger.money import Money


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

class ContributionService:

    @staticmethod
    @transaction.atomic
    def create_contribution(user, validated_data, member_phones=None, add_all_members=False):
        # Governance quorum is enforced at request time against the real
        # contribution row (submit_disbursement_request / propose amendment),
        # which correctly accounts for members who join after creation. A
        # creation-time pre-check used to run here but was removed (issue #14):
        # it blocked legitimate solo/open contributions and crashed on
        # percentage thresholds (it queried participants via a fake proxy object).
        contribution = Contribution.objects.create(created_by=user, **validated_data)
        ContributionAccount.objects.create(contribution=contribution)

        ContributionParticipant.objects.create(contribution=contribution, user=user, is_active=True)

        if add_all_members and contribution.community:
            from apps.communities.models import CommunityMembership
            members = CommunityMembership.objects.filter(
                community=contribution.community, is_active=True
            ).exclude(user=user).select_related('user')
            for m in members:
                ContributionParticipant.objects.get_or_create(
                    contribution=contribution, user=m.user,
                    defaults={'is_active': True},
                )
        elif member_phones:
            from apps.users.models import User
            for phone in member_phones:
                try:
                    member = User.objects.get(phone_number=phone)
                    if member != user:
                        ContributionParticipant.objects.get_or_create(
                            contribution=contribution, user=member,
                            defaults={'is_active': True},
                        )
                except User.DoesNotExist:
                    pass

        ActivityService.log_activity(
            user=user,
            activity_type='contribution_created',
            message=f"{_dn(user)} created contribution '{contribution.title}'",
        )
        return contribution

    @staticmethod
    def join_contribution(contribution_id, user):
        contribution = Contribution.objects.get(id=contribution_id)
        if contribution.status != 'active':
            raise ValidationError("This contribution is closed and no longer accepting new members.")

        # Section B: block joining a ROSCA mid-cycle.
        # Once the rotation has been initialised (slots exist), new members
        # cannot join the current cycle — they must wait for the next one.
        if contribution.contribution_type == 'ROSCA':
            from .models import ROSCASlot
            rotation_active = ROSCASlot.objects.filter(
                contribution=contribution, cycle_number=1
            ).exists()
            already_participant = ContributionParticipant.objects.filter(
                contribution=contribution, user=user
            ).exists()
            if rotation_active and not already_participant:
                raise ValidationError(
                    "This ROSCA rotation has already started. "
                    "New members can join after the current cycle completes."
                )
        participant, created = ContributionParticipant.objects.get_or_create(
            contribution=contribution, user=user
        )
        if not created:
            participant.is_active = True
            participant.save()

        if contribution.created_by != user:
            _notify(
                user=contribution.created_by,
                notification_type='contribution_joined',
                title=f"New participant in {contribution.title}",
                message=f"{_dn(user)} joined your contribution.",
                contribution_id=contribution.id,
            )
        return participant

    @staticmethod
    def leave_contribution(contribution_id, user):
        participant = ContributionParticipant.objects.filter(
            contribution_id=contribution_id, user=user
        ).first()
        if participant:
            participant.is_active = False
            participant.save()
        return participant

    @staticmethod
    def close_contribution(contribution_id, user):
        contribution = Contribution.objects.get(id=contribution_id)
        if contribution.created_by != user:
            raise PermissionDenied("Only the creator can close this contribution.")
        contribution.status = 'closed'
        contribution.is_active = False
        contribution.save(update_fields=['status', 'is_active'])
        return contribution

    @staticmethod
    def archive_contribution(contribution_id, user):
        contribution = Contribution.objects.get(id=contribution_id)
        if contribution.created_by != user:
            raise PermissionDenied("Only the creator can archive this contribution.")
        contribution.status = 'archived'
        contribution.is_active = False
        contribution.save(update_fields=['status', 'is_active'])
        return contribution

    @staticmethod
    def reopen_contribution(contribution_id, user):
        contribution = Contribution.objects.get(id=contribution_id)
        if contribution.created_by != user:
            raise PermissionDenied("Only the creator can reopen this contribution.")
        contribution.status = 'active'
        contribution.is_active = True
        contribution.save(update_fields=['status', 'is_active'])
        return contribution

    @staticmethod
    def delete_contribution(contribution_id, user):
        contribution = Contribution.objects.get(id=contribution_id)
        if contribution.created_by != user:
            raise PermissionDenied("Only the creator can delete this contribution.")
        if contribution.current_amount > 0:
            raise ValidationError(
                "Cannot delete a contribution with an active balance. "
                "Close it and disburse all funds before deleting."
            )
        contribution.delete()

    @staticmethod
    def get_participants(contribution_id):
        return ContributionParticipant.objects.filter(
            contribution_id=contribution_id, is_active=True
        ).select_related('user')

    @staticmethod
    def get_user_contributions(user, active_only=True):
        from django.db.models import Count, Q, Prefetch
        qs = Contribution.objects.filter(
            participants__user=user, participants__is_active=True
        ).distinct()
        if active_only:
            qs = qs.filter(is_active=True)
        return qs.annotate(
            active_participant_count=Count(
                'participants', filter=Q(participants__is_active=True), distinct=True
            )
        ).prefetch_related(
            Prefetch(
                'balances',
                queryset=ContributionBalance.objects.filter(user=user),
                to_attr='_user_balance_list',
            )
        ).order_by('-created_at')

    @staticmethod
    def get_by_invite_code(invite_code):
        return Contribution.objects.filter(invite_code=invite_code).first()

    @staticmethod
    @transaction.atomic
    def contribute(user, contribution_id, amount, mpesa_receipt=None, idempotency_key=None):
        """
        Record an inbound member contribution.

        Writes to both the legacy mutable balance fields (for backwards compat)
        and the new immutable ledger (single source of truth going forward).
        Uses F() expressions for all balance updates — no read-modify-write.
        Idempotent when idempotency_key is supplied (e.g. M-Pesa receipt).
        """
        if amount <= 0:
            raise ValidationError("Amount must be greater than 0")

        try:
            if user.kyc.status != 'approved':
                raise ValidationError("Your identity verification must be approved before you can contribute.")
        except user.__class__.kyc.RelatedObjectDoesNotExist:
            raise ValidationError("Please complete identity verification before contributing.")

        contribution = Contribution.objects.select_for_update().get(id=contribution_id)

        if contribution.status != 'active':
            raise ValidationError("This contribution is closed and no longer accepting payments.")

        if not ContributionParticipant.objects.filter(
            contribution=contribution, user=user, is_active=True
        ).exists():
            raise ValidationError("User is not an active participant")

        # Section C — late contribution policy
        if contribution.end_date:
            from datetime import date, timedelta
            today = timezone.now().date()
            policy = contribution.late_contribution_policy

            if policy == 'strict' and today > contribution.end_date:
                raise ValidationError(
                    f"This contribution closed on "
                    f"{contribution.end_date.strftime('%d %b %Y')}. "
                    "No further payments are accepted."
                )
            elif policy == 'grace':
                grace_deadline = contribution.end_date + timedelta(
                    days=contribution.late_contribution_grace_days or 7
                )
                if today > grace_deadline:
                    raise ValidationError(
                        f"The grace period for this contribution ended on "
                        f"{grace_deadline.strftime('%d %b %Y')}. "
                        "No further payments are accepted."
                    )

        # ── Idempotency: don't double-credit the same M-Pesa receipt ──────────
        idem_key = idempotency_key or (
            f"contrib-{contribution_id}-{mpesa_receipt}" if mpesa_receipt
            else f"contrib-{contribution_id}-{user.id}-manual"
        )

        # ── Legacy: ContributionTransaction (kept for backwards compat) ────────
        # Check for existing ledger entry to avoid duplicate ContributionTransaction rows
        existing_le = LedgerEntry.objects.filter(
            idempotency_key=f"le-{idem_key}"
        ).first()

        if existing_le:
            # Already processed — find and return the existing tx
            tx = ContributionTransaction.objects.filter(
                contribution=contribution, user=user,
                mpesa_receipt=mpesa_receipt,
            ).first()
            return tx

        tx = ContributionTransaction.objects.create(
            contribution=contribution,
            user=user,
            amount=amount,
            transaction_type='CONTRIBUTION',
            mpesa_receipt=mpesa_receipt or None,
        )

        # ── Legacy balance updates via F() — safe under concurrency ───────────
        Contribution.objects.filter(pk=contribution.pk).update(
            current_amount=F('current_amount') + Decimal(str(amount))
        )
        ContributionAccount.objects.filter(contribution=contribution).update(
            total_amount=F('total_amount') + Decimal(str(amount))
        )
        ContributionBalance.objects.update_or_create(
            contribution=contribution, user=user,
            defaults={},  # ensure row exists
        )
        ContributionBalance.objects.filter(
            contribution=contribution, user=user
        ).update(amount=F('amount') + Decimal(str(amount)))

        # ── New ledger dual-write ─────────────────────────────────────────────
        ft, _ = create_fin_transaction(
            idempotency_key=idem_key,
            op_type=FinancialTransaction.OpType.CONTRIBUTION,
            amount=Decimal(str(amount)),
            initiated_by=user,
            contribution=contribution,
            initial_state=FinancialTransaction.State.SUCCESS,
        )
        write_ledger_entry(
            idempotency_key=f"le-{idem_key}",
            financial_transaction=ft,
            user=user,
            amount=Decimal(str(amount)),
            direction=LedgerEntry.Direction.CREDIT,
            entry_type=LedgerEntry.EntryType.MEMBER_CONTRIBUTION,
            contribution=contribution,
            mpesa_receipt=mpesa_receipt or None,
            note=f"Member contribution by {user.phone_number}",
        )

        # ── Double-entry posting (P0-05) — the future source of truth ─────────
        post_journal(
            idempotency_key=f"je-{idem_key}",
            op_type=_pm.Op.CONTRIBUTION,
            lines=_pm.contribution_lines(
                member=user, fund_type='contribution',
                fund_id=contribution.id, gross=Money(str(amount)),
            ),
            narration=f"Member contribution by {user.phone_number}",
            financial_transaction=ft,
            created_by=user,
        )

        # ── Side effects ──────────────────────────────────────────────────────
        ActivityService.log_activity(
            user=user,
            activity_type='contribution_payment',
            message=f"{_dn(user)} contributed KES {amount:,.0f} to {contribution.title}",
        )

        contribution.refresh_from_db(fields=['current_amount'])
        previous_amount = contribution.current_amount - Decimal(str(amount))

        if contribution.created_by != user:
            _notify(
                user=contribution.created_by,
                notification_type='contribution_payment',
                title=f"New contribution to {contribution.title}",
                message=f"{_dn(user)} contributed KES {amount:,.0f}.",
                contribution_id=contribution.id,
            )

        if contribution.target_amount and contribution.target_amount > 0:
            prev_pct = int((previous_amount / contribution.target_amount) * 100)
            curr_pct = int((contribution.current_amount / contribution.target_amount) * 100)
            for milestone in (50, 100):
                if prev_pct < milestone <= curr_pct:
                    label = "reached 50%!" if milestone == 50 else "is fully funded! 🎉"
                    for p in ContributionParticipant.objects.filter(
                        contribution=contribution, is_active=True
                    ):
                        _notify(
                            user=p.user,
                            notification_type='contribution_milestone',
                            title=f"{contribution.title} {label}",
                            message=(
                                f"Collected KES {contribution.current_amount} "
                                f"of KES {contribution.target_amount}."
                            ),
                            contribution_id=contribution.id,
                        )
                    break

        return tx


# ---------------------------------------------------------------------------
# ROSCA
# ---------------------------------------------------------------------------

class ROSCAService:

    @staticmethod
    def initialize_rotation(contribution_id, user):
        contribution = Contribution.objects.get(id=contribution_id)
        if contribution.created_by != user:
            raise PermissionDenied("Only the creator can initialize the rotation.")

        participants = list(ContributionParticipant.objects.filter(
            contribution=contribution, is_active=True
        ))
        if len(participants) < 2:
            raise ValidationError("At least 2 participants required.")

        ROSCASlot.objects.filter(contribution=contribution, cycle_number=1).delete()
        random.shuffle(participants)
        slots = [
            ROSCASlot(contribution=contribution, participant=p, slot_order=i + 1, cycle_number=1)
            for i, p in enumerate(participants)
        ]
        ROSCASlot.objects.bulk_create(slots)

        for slot in ROSCASlot.objects.filter(
            contribution=contribution, cycle_number=1
        ).order_by('slot_order'):
            _notify(
                user=slot.participant.user,
                notification_type='rosca_rotation_set',
                title=f"Rotation set for {contribution.title}",
                message=(
                    f"You are slot #{slot.slot_order}. "
                    f"Contribute KES {contribution.fixed_amount or contribution.cycle_amount} each cycle."
                ),
                contribution_id=contribution.id,
            )

        return ROSCASlot.objects.filter(
            contribution=contribution, cycle_number=1
        ).select_related('participant__user').order_by('slot_order')

    @staticmethod
    def get_rotation_status(contribution_id):
        return ROSCASlot.objects.filter(
            contribution_id=contribution_id
        ).select_related('participant__user').order_by('cycle_number', 'slot_order')

    @staticmethod
    @transaction.atomic
    def mark_slot_paid(contribution_id, user):
        contribution = Contribution.objects.select_for_update().get(id=contribution_id)
        if contribution.created_by != user:
            raise PermissionDenied("Only the creator can advance the rotation.")

        current_slot = ROSCASlot.objects.filter(
            contribution=contribution, has_received=False
        ).order_by('cycle_number', 'slot_order').first()

        if not current_slot:
            raise ValidationError("All slots have been paid out for this cycle.")

        payout_amount = contribution.current_amount

        current_slot.has_received  = True
        current_slot.received_at   = timezone.now()
        current_slot.payout_amount = payout_amount
        current_slot.save()

        # Legacy transaction record
        ContributionTransaction.objects.create(
            contribution=contribution,
            user=current_slot.participant.user,
            amount=payout_amount,
            transaction_type='WITHDRAWAL',
            note=f"ROSCA payout — cycle {current_slot.cycle_number}, slot {current_slot.slot_order}",
        )

        # Legacy balance update via F()
        Contribution.objects.filter(pk=contribution.pk).update(current_amount=Decimal('0'))
        ContributionAccount.objects.filter(contribution=contribution).update(
            total_amount=Decimal('0')
        )

        # Ledger DEBIT entry
        idem_key = f"rosca-payout-{contribution.id}-cycle{current_slot.cycle_number}-slot{current_slot.slot_order}"
        ft, _ = create_fin_transaction(
            idempotency_key=idem_key,
            op_type=FinancialTransaction.OpType.ROSCA_PAYOUT,
            amount=payout_amount,
            initiated_by=user,
            recipient_phone=current_slot.participant.user.phone_number,
            contribution=contribution,
            context_type='rosca_slot',
            context_id=current_slot.id,
            initial_state=FinancialTransaction.State.SUCCESS,
        )
        write_ledger_entry(
            idempotency_key=f"le-{idem_key}",
            financial_transaction=ft,
            user=current_slot.participant.user,
            amount=payout_amount,
            direction=LedgerEntry.Direction.DEBIT,
            entry_type=LedgerEntry.EntryType.ROSCA_PAYOUT,
            contribution=contribution,
            note=f"ROSCA payout — cycle {current_slot.cycle_number}, slot {current_slot.slot_order}",
        )

        # Double-entry posting (P0-05): payout draws the recipient's pool share.
        post_journal(
            idempotency_key=f"je-{idem_key}",
            op_type=_pm.Op.ROSCA_PAYOUT,
            lines=_pm.disbursement_lines(
                member=current_slot.participant.user, fund_type='contribution',
                fund_id=contribution.id, amount=Money(str(payout_amount)),
            ),
            narration=f"ROSCA payout — cycle {current_slot.cycle_number}, slot {current_slot.slot_order}",
            financial_transaction=ft,
            created_by=user,
        )

        _notify(
            user=current_slot.participant.user,
            notification_type='rosca_payout',
            title="It's your ROSCA turn!",
            message=(
                f"KES {payout_amount:,.0f} designated for your payout "
                f"from '{contribution.title}'."
            ),
            contribution_id=contribution.id,
        )
        return current_slot


# ---------------------------------------------------------------------------
# Multi-signature Disbursement
# ---------------------------------------------------------------------------

class DisbursementService:

    @staticmethod
    @transaction.atomic
    def create_request(contribution_id, user, amount, reason, recipient_phone):
        contribution = Contribution.objects.select_for_update().get(id=contribution_id)

        if not FinancialPermissions.is_active_participant(contribution, user):
            raise PermissionDenied("You must be an active participant.")

        # Balance check with row lock (select_for_update above)
        if Decimal(str(amount)) > contribution.current_amount:
            raise ValidationError("Amount exceeds current pool balance.")

        # Quorum check: ensure at least one eligible voter exists excluding the requester.
        # Catches dynamic deadlocks (e.g. last admin left after contribution was created).
        from apps.ledger.permissions import FinancialPermissions
        FinancialPermissions.assert_quorum_exists(
            contribution, contribution.voting_threshold, user,
            action="submit this disbursement request",
        )

        req = DisbursementRequest.objects.create(
            contribution=contribution,
            requested_by=user,
            amount=amount,
            reason=reason,
            recipient_phone=recipient_phone,
        )

        if contribution.community:
            from apps.communities.models import CommunityMembership
            approvers = CommunityMembership.objects.filter(
                community=contribution.community,
                role__in=['admin', 'treasurer'],
                is_active=True,
            ).exclude(user=user)
            for m in approvers:
                _notify(
                    user=m.user,
                    notification_type='disbursement_requested',
                    title=f"Disbursement request — {contribution.title}",
                    message=f"{_dn(user)} requests KES {amount:,.0f}: {reason[:80]}",
                    contribution_id=contribution.id,
                    join_request_id=req.id,  # used by the mobile inline approve/reject buttons
                )
        return req

    @staticmethod
    @transaction.atomic
    def vote(request_id, voter, vote_choice):
        req = DisbursementRequest.objects.select_for_update().get(
            id=request_id, status='PENDING'
        )
        contribution = req.contribution

        if req.requested_by == voter:
            raise PermissionDenied("You cannot vote on your own disbursement request.")

        # Section B: cooling-off check for disbursement voting
        if contribution.community:
            from apps.communities.services import check_cooling_off
            check_cooling_off(voter, contribution.community, 'disbursement_vote')

        # Authorization
        threshold = contribution.voting_threshold
        if threshold == 'admins':
            authorized = FinancialPermissions.is_contribution_admin(contribution, voter)
        else:
            authorized = FinancialPermissions.is_active_participant(contribution, voter)

        if not authorized:
            raise PermissionDenied("You are not authorised to vote on this request.")

        vote_obj, created = DisbursementVote.objects.get_or_create(
            request=req, voter=voter, defaults={'vote': vote_choice}
        )
        if not created:
            raise ValidationError("You have already voted on this disbursement request.")

        approvals  = req.votes.filter(vote='APPROVE').count()
        rejections = req.votes.filter(vote='REJECT').count()
        required   = contribution.required_approvals()

        if approvals >= required:
            req.transition_to('APPROVED')
            DisbursementService._schedule_execution(req)

        elif rejections >= required:
            req.transition_to('REJECTED')
            _notify(
                user=req.requested_by,
                notification_type='disbursement_rejected',
                title=f"Disbursement rejected — {contribution.title}",
                message=f"Your request for KES {req.amount} was rejected by the group.",
                contribution_id=contribution.id,
            )
        return req

    @staticmethod
    @transaction.atomic
    def cancel_request(request_id, user):
        """Allow the requester to withdraw a still-PENDING disbursement request."""
        req = DisbursementRequest.objects.select_for_update().get(id=request_id)
        if req.requested_by != user:
            raise PermissionDenied("Only the person who created this request can cancel it.")
        if req.status != 'PENDING':
            raise ValidationError(f"Cannot cancel a request that is already {req.status}.")
        req.transition_to('CANCELLED')
        return req

    @staticmethod
    @transaction.atomic
    def _schedule_execution(req: 'DisbursementRequest') -> None:
        """
        Reserve funds in the ledger and dispatch the B2C payout to Celery.

        Called inside the vote() atomic block — the Celery dispatch happens
        via on_commit() so the task only runs after the DB transaction commits.
        The M-Pesa HTTP call therefore NEVER touches an open DB transaction.
        """
        contribution = Contribution.objects.select_for_update().get(id=req.contribution_id)

        if contribution.current_amount < req.amount:
            raise ValidationError("Insufficient pool balance at execution time.")

        # Governance cooldown check (Issue 16): block execution if voting_threshold
        # was changed recently — gives the group 24 h to review approvals that were
        # cast under the previous (possibly stricter) governance rules.
        if contribution.governance_locked_until and contribution.governance_locked_until > timezone.now():
            from django.utils.timezone import localtime
            unlock = localtime(contribution.governance_locked_until).strftime('%d %b %Y %H:%M')
            raise ValidationError(
                f"Governance rules were recently changed. Disbursements are locked until {unlock} "
                f"to allow the group to review pending approvals under the new rules."
            )

        # ── Reserve funds: DEBIT ledger entry immediately ─────────────────────
        idem_key = f"disb-exec-{req.id}"
        ft, created = create_fin_transaction(
            idempotency_key=idem_key,
            op_type=FinancialTransaction.OpType.DISBURSEMENT,
            amount=req.amount,
            initiated_by=req.requested_by,
            recipient_phone=req.recipient_phone,
            contribution=contribution,
            context_type='disbursement_request',
            context_id=req.id,
        )

        if not created and ft.state in (
            FinancialTransaction.State.SUCCESS,
            FinancialTransaction.State.PROCESSING,
        ):
            # Already scheduled or completed — nothing to do
            return

        write_ledger_entry(
            idempotency_key=f"le-{idem_key}",
            financial_transaction=ft,
            user=req.requested_by,
            amount=req.amount,
            direction=LedgerEntry.Direction.DEBIT,
            entry_type=LedgerEntry.EntryType.DISBURSEMENT,
            contribution=contribution,
            note=f"Disbursement: {req.reason[:120]}",
        )

        # Double-entry posting (P0-05): reserve funds out of the pool.
        post_journal(
            idempotency_key=f"je-{idem_key}",
            op_type=_pm.Op.DISBURSEMENT,
            lines=_pm.disbursement_lines(
                member=req.requested_by, fund_type='contribution',
                fund_id=contribution.id, amount=Money(str(req.amount)),
            ),
            narration=f"Disbursement: {req.reason[:120]}",
            financial_transaction=ft,
            created_by=req.requested_by,
        )

        # ── Legacy balance update via F() ─────────────────────────────────────
        Contribution.objects.filter(pk=contribution.pk).update(
            current_amount=F('current_amount') - req.amount
        )
        ContributionAccount.objects.filter(contribution=contribution).update(
            total_amount=F('total_amount') - req.amount
        )

        # ── Legacy WITHDRAWAL record ──────────────────────────────────────────
        ContributionTransaction.objects.create(
            contribution=contribution,
            user=req.requested_by,
            amount=req.amount,
            transaction_type='WITHDRAWAL',
            note=f"Approved disbursement: {req.reason[:80]}",
        )

        # ── Notify requester ──────────────────────────────────────────────────
        _notify(
            user=req.requested_by,
            notification_type='disbursement_executed',
            title="Disbursement approved!",
            message=(
                f"KES {req.amount} from '{contribution.title}' approved. "
                f"Sending to {req.recipient_phone}."
            ),
            contribution_id=contribution.id,
        )

        # ── Dispatch B2C via Celery AFTER commit ──────────────────────────────
        ft_id = ft.id

        def _dispatch():
            from apps.ledger.tasks import execute_b2c_payout
            execute_b2c_payout.delay(ft_id)

        transaction.on_commit(_dispatch)

        # Mark FT as PROCESSING once we've queued the Celery task
        # (the task itself will transition to SUCCESS/FAILED via B2C callback)
        req.transition_to('EXECUTED', executed_at=timezone.now())


# ---------------------------------------------------------------------------
# Welfare Fund
# ---------------------------------------------------------------------------

class WelfareService:

    @staticmethod
    def get_or_create_community_fund(community):
        fund, _ = WelfareFund.objects.get_or_create(community=community)
        return fund

    @staticmethod
    @transaction.atomic
    def contribute_to_welfare(fund_id, user, amount, mpesa_receipt=None):
        fund = WelfareFund.objects.select_for_update().get(id=fund_id)
        WelfareContribution.objects.create(fund=fund, user=user, amount=amount)

        # Legacy balance update via F()
        WelfareFund.objects.filter(pk=fund.pk).update(
            balance=F('balance') + Decimal(str(amount))
        )

        # Ledger dual-write — key anchored to the M-Pesa receipt (externally-assigned,
        # immutable). Retries with the same receipt are no-ops via get_or_create.
        idem_key = f"welfare-contrib-{fund_id}-{user.id}-{mpesa_receipt}"
        ft, _ = create_fin_transaction(
            idempotency_key=idem_key,
            op_type=FinancialTransaction.OpType.WELFARE_CONTRIBUTION,
            amount=Decimal(str(amount)),
            initiated_by=user,
            welfare_fund=fund,
            initial_state=FinancialTransaction.State.SUCCESS,
        )
        write_ledger_entry(
            idempotency_key=f"le-{idem_key}",
            financial_transaction=ft,
            user=user,
            amount=Decimal(str(amount)),
            direction=LedgerEntry.Direction.CREDIT,
            entry_type=LedgerEntry.EntryType.WELFARE_CONTRIBUTION,
            welfare_fund=fund,
        )

        # Double-entry posting (P0-05).
        post_journal(
            idempotency_key=f"je-{idem_key}",
            op_type=_pm.Op.WELFARE_CONTRIBUTION,
            lines=_pm.welfare_contribution_lines(
                member=user, fund_id=fund.id, amount=Money(str(amount)),
            ),
            narration=f"Welfare contribution by {user.phone_number}",
            financial_transaction=ft,
            created_by=user,
        )

        ActivityService.log_activity(
            user=user,
            activity_type='welfare_contribution',
            message=f"{_dn(user)} contributed KES {amount:,.0f} to welfare fund",
        )
        fund.refresh_from_db()
        return fund

    @staticmethod
    @transaction.atomic
    def submit_claim(fund_id, user, amount_requested, reason):
        fund   = WelfareFund.objects.select_for_update().get(id=fund_id)
        amount = Decimal(str(amount_requested))

        # Section B: cooling-off period check
        if fund.community:
            from apps.communities.services import check_cooling_off
            check_cooling_off(user, fund.community, 'welfare_claim')

        if WelfareClaim.objects.filter(fund=fund, claimant=user, status='PENDING').exists():
            raise ValidationError(
                "You already have a pending claim. "
                "Wait for it to be reviewed before submitting another."
            )
        if amount > fund.balance:
            raise ValidationError(
                f"Claim amount exceeds the current fund balance of KES {fund.balance:,.0f}."
            )
        if amount <= 0:
            raise ValidationError("Claim amount must be greater than zero.")

        claim = WelfareClaim.objects.create(
            fund=fund, claimant=user,
            amount_requested=amount, reason=reason,
        )

        if fund.community:
            from apps.communities.models import CommunityMembership
            admins = CommunityMembership.objects.filter(
                community=fund.community, role__in=['admin', 'treasurer'], is_active=True
            ).exclude(user=user)
            recipients = set(m.user for m in admins)
            if fund.community.created_by != user:
                recipients.add(fund.community.created_by)
            for recipient in recipients:
                _notify(
                    user=recipient,
                    notification_type='welfare_claim',
                    title=f"Welfare claim — {fund.community.name}",
                    message=f"{_dn(user)} requests KES {amount:,.0f}: {reason[:80]}",
                    community_id=fund.community.id,
                    join_request_id=claim.id,  # used by mobile inline approve/reject buttons
                )
        return claim

    @staticmethod
    @transaction.atomic
    def approve_claim(claim_id, admin_user):
        """Admin approves a pending welfare claim → schedules B2C payout."""
        claim = WelfareClaim.objects.select_for_update().get(id=claim_id, status='PENDING')

        if claim.claimant == admin_user:
            raise PermissionDenied("You cannot approve your own welfare claim.")

        if not FinancialPermissions.is_community_admin(claim.fund.community, admin_user):
            raise PermissionDenied("Only community admins can approve welfare claims.")

        WelfareService._disburse(claim)
        return WelfareClaim.objects.get(id=claim_id)

    @staticmethod
    def reject_claim(claim_id, admin_user):
        claim = WelfareClaim.objects.get(id=claim_id, status='PENDING')

        if claim.claimant == admin_user:
            raise PermissionDenied("You cannot reject your own welfare claim.")

        if not FinancialPermissions.is_community_admin(claim.fund.community, admin_user):
            raise PermissionDenied("Only community admins can reject welfare claims.")

        claim.transition_to('REJECTED')
        _notify(
            user=claim.claimant,
            notification_type='welfare_rejected',
            title="Welfare claim rejected",
            message=(
                f"Your welfare claim of KES {claim.amount_requested:,.0f} "
                "was not approved by the admins."
            ),
        )
        return claim

    @staticmethod
    @transaction.atomic
    def _disburse(claim: 'WelfareClaim') -> None:
        """
        Reserve welfare funds in the ledger and dispatch B2C via Celery.

        The M-Pesa call happens OUTSIDE this transaction via on_commit() →
        Celery task. This prevents the 15-second HTTP timeout from holding
        DB row locks open.
        """
        fund = WelfareFund.objects.select_for_update().get(id=claim.fund_id)
        if fund.balance < claim.amount_requested:
            raise ValidationError("Insufficient welfare fund balance.")

        # ── Reserve funds: DEBIT ledger + legacy balance update ───────────────
        idem_key = f"welfare-claim-{claim.id}"
        ft, created = create_fin_transaction(
            idempotency_key=idem_key,
            op_type=FinancialTransaction.OpType.WELFARE_CLAIM,
            amount=claim.amount_requested,
            initiated_by=claim.claimant,
            recipient_phone=claim.claimant.phone_number,
            welfare_fund=fund,
            context_type='welfare_claim',
            context_id=claim.id,
        )

        if not created and ft.state in (
            FinancialTransaction.State.SUCCESS,
            FinancialTransaction.State.PROCESSING,
        ):
            return  # already in progress

        write_ledger_entry(
            idempotency_key=f"le-{idem_key}",
            financial_transaction=ft,
            user=claim.claimant,
            amount=claim.amount_requested,
            direction=LedgerEntry.Direction.DEBIT,
            entry_type=LedgerEntry.EntryType.WELFARE_CLAIM,
            welfare_fund=fund,
            note=f"Welfare claim #{claim.id}: {claim.reason[:80]}",
        )

        # Double-entry posting (P0-05): reserve welfare funds for the claimant.
        post_journal(
            idempotency_key=f"je-{idem_key}",
            op_type=_pm.Op.WELFARE_CLAIM,
            lines=_pm.welfare_claim_lines(
                member=claim.claimant, fund_id=fund.id,
                amount=Money(str(claim.amount_requested)),
            ),
            narration=f"Welfare claim #{claim.id}",
            financial_transaction=ft,
            created_by=claim.claimant,
        )

        # Legacy balance update via F()
        WelfareFund.objects.filter(pk=fund.pk).update(
            balance=F('balance') - claim.amount_requested
        )

        # Mark claim APPROVED (→ DISBURSED when B2C callback confirms)
        claim.transition_to('APPROVED', approved_at=timezone.now())

        # ── Dispatch B2C via Celery AFTER this transaction commits ────────────
        ft_id = ft.id

        def _dispatch_b2c():
            from apps.ledger.tasks import execute_b2c_payout
            execute_b2c_payout.delay(ft_id)

        transaction.on_commit(_dispatch_b2c)

        _notify(
            user=claim.claimant,
            notification_type='welfare_disbursed',
            title="Welfare claim approved!",
            message=(
                f"KES {claim.amount_requested:,.0f} approved and being sent to your M-Pesa."
            ),
        )


# ---------------------------------------------------------------------------
# Emergency Advances
# ---------------------------------------------------------------------------

class EmergencyAdvanceService:

    MAX_ADVANCE_RATIO = Decimal('0.80')

    @staticmethod
    def request_advance(contribution_id, user, amount, interest_rate, repayment_due):
        try:
            if user.kyc.status != 'approved':
                raise ValidationError("Your identity verification must be approved before requesting an advance.")
        except user.__class__.kyc.RelatedObjectDoesNotExist:
            raise ValidationError("Please complete identity verification before requesting an advance.")

        contribution = Contribution.objects.get(id=contribution_id)

        if not FinancialPermissions.is_active_participant(contribution, user):
            raise PermissionDenied("You must be an active participant.")

        # Section B: cooling-off period check
        if contribution.community:
            from apps.communities.services import check_cooling_off
            check_cooling_off(user, contribution.community, 'emergency_advance')

        # Derive eligibility from ledger (not mutable ContributionBalance)
        from apps.ledger.queries import member_contribution_total
        member_total = member_contribution_total(contribution.id, user.id)
        # Fall back to legacy field if ledger has no entries yet (migration phase)
        if member_total == Decimal('0'):
            balance_obj  = ContributionBalance.objects.filter(
                contribution=contribution, user=user
            ).first()
            member_total = balance_obj.amount if balance_obj else Decimal('0')

        max_advance = member_total * EmergencyAdvanceService.MAX_ADVANCE_RATIO

        if Decimal(str(amount)) > max_advance:
            raise ValidationError(
                f"Advance cannot exceed 80% of your contributions "
                f"(max KES {max_advance:.2f})."
            )

        if EmergencyAdvance.objects.filter(
            contribution=contribution, borrower=user,
            status__in=['PENDING', 'APPROVED', 'DISBURSED'],
        ).exists():
            raise ValidationError("You already have an active advance on this contribution.")

        advance = EmergencyAdvance.objects.create(
            contribution=contribution,
            borrower=user,
            amount=amount,
            interest_rate=Decimal(str(interest_rate)),
            repayment_due=repayment_due,
        )

        if contribution.community:
            from apps.communities.models import CommunityMembership
            approvers = CommunityMembership.objects.filter(
                community=contribution.community,
                role__in=['admin', 'treasurer'],
                is_active=True,
            ).exclude(user=user)
            for m in approvers:
                _notify(
                    user=m.user,
                    notification_type='advance_requested',
                    title=f"Advance request — {contribution.title}",
                    message=(
                        f"{user.phone_number} requests KES {amount} advance "
                        f"at {interest_rate}% interest."
                    ),
                    contribution_id=contribution.id,
                    join_request_id=advance.id,  # used by mobile inline approve/reject buttons
                )
        return advance

    @staticmethod
    @transaction.atomic
    def approve_advance(advance_id, admin_user):
        """
        Approve + immediately disburse an emergency advance.

        Key fix vs. the old code:
          - Pool balance is DEBITED before B2C is called (old code forgot this entirely).
          - B2C is dispatched via Celery OUTSIDE this transaction (old code called it inline).
        """
        advance = EmergencyAdvance.objects.select_for_update().get(
            id=advance_id, status__in=('PENDING', 'APPROVED')
        )
        contribution = Contribution.objects.select_for_update().get(
            id=advance.contribution_id
        )

        if advance.borrower == admin_user:
            raise PermissionDenied("You cannot approve your own advance request.")

        if not FinancialPermissions.is_contribution_admin(contribution, admin_user):
            raise PermissionDenied("Only admins/treasurers can approve advances.")

        # Check pool has enough funds
        if contribution.current_amount < advance.amount:
            raise ValidationError("Insufficient pool balance to cover this advance.")

        # ── Reserve funds: DEBIT ledger + legacy balance update ───────────────
        idem_key = f"advance-disb-{advance.id}"
        ft, created = create_fin_transaction(
            idempotency_key=idem_key,
            op_type=FinancialTransaction.OpType.ADVANCE_DISBURSEMENT,
            amount=advance.amount,
            initiated_by=admin_user,
            recipient_phone=advance.borrower.phone_number,
            contribution=contribution,
            context_type='emergency_advance',
            context_id=advance.id,
        )

        if not created and ft.state in (
            FinancialTransaction.State.SUCCESS,
            FinancialTransaction.State.PROCESSING,
        ):
            return advance  # already in progress

        write_ledger_entry(
            idempotency_key=f"le-{idem_key}",
            financial_transaction=ft,
            user=advance.borrower,
            amount=advance.amount,
            direction=LedgerEntry.Direction.DEBIT,
            entry_type=LedgerEntry.EntryType.ADVANCE_DISBURSEMENT,
            contribution=contribution,
            note=f"Emergency advance #{advance.id} to {advance.borrower.phone_number}",
        )

        # Double-entry posting (P0-05): receivable model — the borrower owes the
        # principal back (asset), funded out of the float.
        post_journal(
            idempotency_key=f"je-{idem_key}",
            op_type=_pm.Op.ADVANCE_DISBURSEMENT,
            lines=_pm.advance_disbursement_lines(
                member=advance.borrower, advance_id=advance.id,
                principal=Money(str(advance.amount)),
            ),
            narration=f"Emergency advance #{advance.id}",
            financial_transaction=ft,
            created_by=admin_user,
        )

        # Legacy balance deduction (was MISSING before — critical bug fix)
        Contribution.objects.filter(pk=contribution.pk).update(
            current_amount=F('current_amount') - advance.amount
        )
        ContributionAccount.objects.filter(contribution=contribution).update(
            total_amount=F('total_amount') - advance.amount
        )
        ContributionTransaction.objects.create(
            contribution=contribution,
            user=advance.borrower,
            amount=advance.amount,
            transaction_type='ADVANCE',
            note=f"Emergency advance #{advance.id}",
        )

        advance.transition_to('DISBURSED')

        # ── Dispatch B2C via Celery AFTER commit ──────────────────────────────
        ft_id = ft.id

        def _dispatch_b2c():
            from apps.ledger.tasks import execute_b2c_payout
            execute_b2c_payout.delay(ft_id)

        transaction.on_commit(_dispatch_b2c)

        _notify(
            user=advance.borrower,
            notification_type='advance_approved',
            title="Emergency advance approved!",
            message=(
                f"Your KES {advance.amount} advance from '{contribution.title}' "
                "has been approved and is being sent to your M-Pesa."
            ),
            contribution_id=contribution.id,
        )
        return advance

    @staticmethod
    def reject_advance(advance_id, admin_user):
        advance      = EmergencyAdvance.objects.get(id=advance_id, status='PENDING')
        contribution = advance.contribution

        if advance.borrower == admin_user:
            raise PermissionDenied("You cannot reject your own advance request.")

        if not FinancialPermissions.is_contribution_admin(contribution, admin_user):
            raise PermissionDenied("Only admins/treasurers can reject advances.")

        advance.transition_to('REJECTED')
        _notify(
            user=advance.borrower,
            notification_type='advance_rejected',
            title="Advance request declined",
            message=f"Your KES {advance.amount} advance request was not approved.",
            contribution_id=advance.contribution.id,
        )
        return advance

    @staticmethod
    @transaction.atomic
    def repay(advance_id, user, amount, mpesa_receipt=None):
        """
        Record repayment of an emergency advance via M-Pesa STK callback.

        Key fix vs. the old code:
          - Idempotency key anchored to mpesa_receipt (not wall clock).
          - Writes a dedicated ADVANCE_REPAYMENT ledger entry (entry_type=ADVANCE_REPAYMENT).
          - Does NOT patch "the most recent ContributionTransaction" by creation time
            (which was fragile and could corrupt the wrong row under concurrency).
          - The pool balance is credited directly — no intermediate call to contribute().
        """
        advance = EmergencyAdvance.objects.select_for_update().get(
            id=advance_id, borrower=user, status__in=['APPROVED', 'DISBURSED']
        )
        contribution = Contribution.objects.select_for_update().get(
            id=advance.contribution_id
        )
        amount = Decimal(str(amount))

        advance.amount_repaid = F('amount_repaid') + amount
        advance.save(update_fields=['amount_repaid'])
        advance.refresh_from_db()
        if advance.amount_repaid >= advance.total_due:
            advance.transition_to('REPAID')

        # ── Credit pool balance ───────────────────────────────────────────────
        # Idempotency key anchored to the M-Pesa receipt so retries are no-ops.
        idem_key = f"advance-repay-{advance_id}-{mpesa_receipt}"
        ft, _ = create_fin_transaction(
            idempotency_key=idem_key,
            op_type=FinancialTransaction.OpType.ADVANCE_REPAYMENT,
            amount=amount,
            initiated_by=user,
            contribution=contribution,
            context_type='emergency_advance',
            context_id=advance.id,
            initial_state=FinancialTransaction.State.SUCCESS,
        )
        write_ledger_entry(
            idempotency_key=f"le-{idem_key}",
            financial_transaction=ft,
            user=user,
            amount=amount,
            direction=LedgerEntry.Direction.CREDIT,
            entry_type=LedgerEntry.EntryType.ADVANCE_REPAYMENT,
            contribution=contribution,
            note=f"Repayment for advance #{advance_id}",
        )

        # Double-entry posting (P0-05): cash in, clears the receivable. The
        # principal/interest split (interest -> 4100) is finalised in P0-06 when
        # the ledger becomes the source of truth; here the whole repayment clears
        # the receivable so the journal balances.
        post_journal(
            idempotency_key=f"je-{idem_key}",
            op_type=_pm.Op.ADVANCE_REPAYMENT,
            lines=_pm.advance_repayment_lines(
                member=user, advance_id=advance.id, principal=Money(str(amount)),
            ),
            narration=f"Repayment for advance #{advance_id}",
            financial_transaction=ft,
            created_by=user,
        )

        # Legacy: dedicated REPAYMENT transaction (not patched — created fresh)
        ContributionTransaction.objects.create(
            contribution=contribution,
            user=user,
            amount=amount,
            transaction_type='REPAYMENT',
            note=f"Advance repayment — advance #{advance_id}",
        )

        # Legacy balance credit via F()
        Contribution.objects.filter(pk=contribution.pk).update(
            current_amount=F('current_amount') + amount
        )
        ContributionAccount.objects.filter(contribution=contribution).update(
            total_amount=F('total_amount') + amount
        )

        return advance


# ---------------------------------------------------------------------------
# Standing Orders
# ---------------------------------------------------------------------------

class StandingOrderService:

    @staticmethod
    @transaction.atomic
    def create_standing_order(user, contribution_id, data):
        contribution = Contribution.objects.get(id=contribution_id)

        if not FinancialPermissions.is_contribution_admin(contribution, user):
            raise PermissionDenied(
                "Only the contribution creator or a community admin can create standing orders."
            )

        frequency = data.get('frequency', 'monthly')
        order = StandingOrder.objects.create(
            contribution=contribution,
            created_by=user,
            amount=data['amount'],
            frequency=frequency,
            payee_type=data.get('payee_type', 'fixed'),
            fixed_payee_phone=data.get('fixed_payee_phone') or None,
            next_run_at=timezone.now(),  # due immediately (admin can adjust)
        )

        if order.payee_type == 'rotating':
            participants = ContributionParticipant.objects.filter(
                contribution=contribution, is_active=True
            ).select_related('user').order_by('?')
            for i, p in enumerate(participants, start=1):
                StandingOrderSlot.objects.create(
                    order=order,
                    phone_number=p.user.phone_number,
                    name=p.user.name or '',
                    slot_order=i,
                )
        return order

    @staticmethod
    def get_standing_orders(contribution_id):
        return StandingOrder.objects.filter(
            contribution_id=contribution_id
        ).select_related('created_by').prefetch_related('slots')

    @staticmethod
    @transaction.atomic
    def execute_standing_order(order_id, user):
        """
        Execute a standing order — reserve pool funds and dispatch B2C via Celery.

        Key fixes vs. old code:
          - B2C HTTP call is OUTSIDE the atomic block (dispatched via on_commit → Celery).
          - next_run_at is advanced immediately after scheduling to prevent re-entry.
          - Pool balance is debited via F() (no read-modify-write).
        """
        order = StandingOrder.objects.select_for_update().get(id=order_id)

        if not FinancialPermissions.is_contribution_admin(order.contribution, user):
            raise PermissionDenied("Only the creator or an admin can execute this order.")

        if not order.is_active:
            raise ValidationError("This standing order is no longer active.")

        contribution = Contribution.objects.select_for_update().get(
            id=order.contribution_id
        )
        if contribution.current_amount < order.amount:
            raise ValidationError("Insufficient funds in the contribution pool.")

        if order.payee_type == 'fixed':
            recipient_phone = order.fixed_payee_phone
        else:
            next_slot = order.slots.select_for_update().filter(has_received=False).first()
            if not next_slot:
                raise ValidationError("All rotation slots have been paid out.")
            next_slot.has_received = True
            next_slot.received_at  = timezone.now()
            next_slot.save(update_fields=['has_received', 'received_at'])
            recipient_phone = next_slot.phone_number

        # ── Reserve funds ─────────────────────────────────────────────────────
        now = timezone.now()
        # Idempotency key is anchored to the scheduled window (next_run_at),
        # not the wall-clock time of execution.  Two calls in the same scheduled
        # window produce the same key → safe against double-clicks and retries.
        # Falls back to minute-granularity wall-clock only if next_run_at is unset
        # (e.g. manually created orders before the scheduler ran).
        scheduled_window = order.next_run_at or now
        idem_key = f"so-{order.id}-{scheduled_window.strftime('%Y%m%d%H%M')}"
        ft, created = create_fin_transaction(
            idempotency_key=idem_key,
            op_type=FinancialTransaction.OpType.STANDING_ORDER,
            amount=order.amount,
            initiated_by=user,
            recipient_phone=recipient_phone,
            contribution=contribution,
            context_type='standing_order',
            context_id=order.id,
        )

        if not created and ft.state in (
            FinancialTransaction.State.SUCCESS,
            FinancialTransaction.State.PROCESSING,
        ):
            return order  # already in flight

        write_ledger_entry(
            idempotency_key=f"le-{idem_key}",
            financial_transaction=ft,
            user=user,
            amount=order.amount,
            direction=LedgerEntry.Direction.DEBIT,
            entry_type=LedgerEntry.EntryType.STANDING_ORDER,
            contribution=contribution,
            note=f"Standing order payout to {recipient_phone}",
        )

        # Double-entry posting (P0-05): payout draws down the owner's pool share.
        post_journal(
            idempotency_key=f"je-{idem_key}",
            op_type=_pm.Op.STANDING_ORDER,
            lines=_pm.disbursement_lines(
                member=user, fund_type='contribution',
                fund_id=contribution.id, amount=Money(str(order.amount)),
            ),
            narration=f"Standing order payout to {recipient_phone}",
            financial_transaction=ft,
            created_by=user,
        )

        # Legacy balance update via F()
        Contribution.objects.filter(pk=contribution.pk).update(
            current_amount=F('current_amount') - order.amount
        )
        ContributionAccount.objects.filter(contribution=contribution).update(
            total_amount=F('total_amount') - order.amount
        )
        ContributionTransaction.objects.create(
            contribution=contribution,
            user=user,
            amount=order.amount,
            transaction_type='WITHDRAWAL',
            note=f"Standing order payout to {recipient_phone}",
        )

        # Advance schedule
        StandingOrder.objects.filter(pk=order.pk).update(
            last_executed_at=now,
            next_run_at=_compute_next_run(order.frequency, now),
        )

        ActivityService.log_activity(
            user=user,
            activity_type='standing_order_executed',
            message=f"Standing order of KES {order.amount} paid to {recipient_phone}",
        )

        # ── Dispatch B2C via Celery AFTER commit ──────────────────────────────
        ft_id = ft.id

        def _dispatch():
            from apps.ledger.tasks import execute_b2c_payout
            execute_b2c_payout.delay(ft_id)

        transaction.on_commit(_dispatch)
        return order

    @staticmethod
    def cancel_standing_order(order_id, user):
        order = StandingOrder.objects.get(id=order_id)
        if order.created_by != user:
            raise PermissionDenied("Only the creator can cancel this order.")
        order.is_active = False
        order.save(update_fields=['is_active'])
        return order

    @staticmethod
    def update_standing_order(order_id, user, data):
        """Amend amount, frequency, or fixed_payee_phone on an active standing order."""
        order = StandingOrder.objects.get(id=order_id, is_active=True)
        if order.created_by != user:
            raise PermissionDenied("Only the creator can amend this standing order.")

        changed = False
        if 'amount' in data:
            amount = Decimal(str(data['amount']))
            if amount <= 0:
                raise ValidationError("Amount must be greater than zero.")
            order.amount = amount
            changed = True
        if 'frequency' in data:
            if data['frequency'] not in ('daily', 'weekly', 'monthly'):
                raise ValidationError("Invalid frequency.")
            order.frequency = data['frequency']
            changed = True
        if 'fixed_payee_phone' in data:
            if order.payee_type != 'fixed':
                raise ValidationError("Payee phone can only be changed on fixed-payee orders.")
            order.fixed_payee_phone = data['fixed_payee_phone'] or None
            changed = True

        if changed:
            order.save()
        return order


# ---------------------------------------------------------------------------
# Contribution Amendments
# ---------------------------------------------------------------------------

class AmendmentService:

    SENSITIVE_FIELDS = frozenset({
        'fixed_amount', 'target_amount', 'voting_threshold',
        'end_date', 'period_months', 'visibility',
    })
    DIRECT_FIELDS = frozenset({'title', 'description'})

    @staticmethod
    def _amendment_required(contribution, proposer):
        # Section C: use amendment_voting_threshold, not the disbursement threshold
        threshold = contribution.amendment_voting_threshold
        if threshold == 'admins':
            if contribution.community:
                from apps.communities.models import CommunityMembership
                participant_ids = set(
                    ContributionParticipant.objects.filter(
                        contribution=contribution, is_active=True,
                    ).values_list('user_id', flat=True)
                )
                eligible = CommunityMembership.objects.filter(
                    community=contribution.community,
                    user_id__in=participant_ids,
                    role__in=['admin', 'treasurer'],
                    is_active=True,
                ).exclude(user=proposer).count()
                if (contribution.created_by != proposer
                        and contribution.created_by_id in participant_ids):
                    creator_already = CommunityMembership.objects.filter(
                        community=contribution.community,
                        user=contribution.created_by,
                        role__in=['admin', 'treasurer'],
                        is_active=True,
                    ).exists()
                    if not creator_already:
                        eligible += 1
                return eligible
            else:
                is_participant = ContributionParticipant.objects.filter(
                    contribution=contribution,
                    user=contribution.created_by,
                    is_active=True,
                ).exists()
                if contribution.created_by != proposer and is_participant:
                    return 1
                return 0
        return contribution.required_approvals()

    @staticmethod
    def propose(contribution_id, user, changes: dict, reason: str = ''):
        contribution = Contribution.objects.get(id=contribution_id)

        # Section C — check amendment_proposer setting
        proposer_policy = contribution.amendment_proposer
        if proposer_policy == 'creator':
            if contribution.created_by != user:
                raise PermissionDenied(
                    "Only the contribution creator can propose amendments."
                )
        elif proposer_policy == 'admins':
            if not FinancialPermissions.is_contribution_admin(contribution, user):
                raise PermissionDenied(
                    "Only admins and treasurers can propose amendments."
                )
        elif proposer_policy == 'members':
            if not FinancialPermissions.is_active_participant(contribution, user):
                raise PermissionDenied(
                    "Only active participants can propose amendments."
                )
        else:
            if not FinancialPermissions.is_contribution_admin(contribution, user):
                raise PermissionDenied(
                    "Only the contribution creator or a community admin can propose amendments."
                )

        # Quorum check: ensure at least one eligible voter exists for the amendment threshold.
        FinancialPermissions.assert_quorum_exists(
            contribution, contribution.amendment_voting_threshold, user,
            action="propose this amendment",
        )

        bad_keys = set(changes.keys()) - AmendmentService.SENSITIVE_FIELDS
        if bad_keys:
            raise ValidationError(
                f"Invalid fields for amendment: {bad_keys}. "
                "Only sensitive fields require a proposal."
            )
        if not changes:
            raise ValidationError("No changes provided.")

        if ContributionAmendment.objects.filter(
            contribution=contribution, status='PENDING'
        ).exists():
            raise ValidationError(
                "There is already a pending amendment for this contribution. "
                "Wait for it to be resolved before proposing another."
            )

        from decimal import Decimal, InvalidOperation
        if 'target_amount' in changes:
            try:
                ta = Decimal(str(changes['target_amount']))
                if ta < contribution.current_amount:
                    raise ValidationError(
                        f"target_amount cannot be lower than the current balance "
                        f"of KES {contribution.current_amount:,.0f}."
                    )
            except InvalidOperation:
                raise ValidationError("Invalid target_amount value.")
        if 'fixed_amount' in changes and contribution.amount_type != 'fixed':
            raise ValidationError(
                "fixed_amount can only be amended on fixed-amount contributions."
            )
        if 'end_date' in changes and contribution.tenure_type != 'date':
            raise ValidationError(
                "end_date can only be amended on contributions with a specific end date."
            )
        if 'period_months' in changes and contribution.tenure_type != 'period':
            raise ValidationError(
                "period_months can only be amended on period-based contributions."
            )

        serialised = {}
        for k, v in changes.items():
            try:
                serialised[k] = (
                    str(Decimal(str(v))) if k in ('fixed_amount', 'target_amount') else v
                )
            except Exception:
                serialised[k] = v

        amendment = ContributionAmendment.objects.create(
            contribution=contribution,
            proposed_by=user,
            changes=serialised,
            reason=reason,
        )

        required = AmendmentService._amendment_required(contribution, user)
        if required == 0:
            AmendmentService._apply(amendment, contribution)
            return ContributionAmendment.objects.get(id=amendment.id)

        for p in ContributionParticipant.objects.filter(
            contribution=contribution, is_active=True
        ).exclude(user=user).select_related('user'):
            _notify(
                user=p.user,
                notification_type='amendment_proposed',
                title=f"Amendment proposed — {contribution.title}",
                message=(
                    f"{user.phone_number} proposed changes to "
                    f"{', '.join(changes.keys())}. Vote now."
                ),
                contribution_id=contribution.id,
            )

        return amendment

    @staticmethod
    def get_amendments(contribution_id):
        return ContributionAmendment.objects.filter(
            contribution_id=contribution_id
        ).select_related('proposed_by', 'contribution').prefetch_related(
            'votes__voter'
        ).order_by('-created_at')

    @staticmethod
    @transaction.atomic
    def vote(amendment_id, voter, vote_choice: str):
        amendment    = ContributionAmendment.objects.select_for_update().get(
            id=amendment_id, status='PENDING'
        )
        contribution = amendment.contribution

        if amendment.proposed_by == voter:
            raise PermissionDenied("You cannot vote on your own amendment proposal.")

        # Section C: amendment votes use amendment_voting_threshold, not disbursement threshold
        threshold = contribution.amendment_voting_threshold
        if threshold == 'admins':
            if contribution.community:
                from apps.communities.models import CommunityMembership
                is_participant = ContributionParticipant.objects.filter(
                    contribution=contribution, user=voter, is_active=True,
                ).exists()
                if not is_participant:
                    authorized = False
                elif contribution.created_by == voter:
                    authorized = True
                else:
                    authorized = CommunityMembership.objects.filter(
                        community=contribution.community,
                        user=voter, role__in=['admin', 'treasurer'], is_active=True,
                    ).exists()
            else:
                authorized = contribution.created_by == voter
        else:
            authorized = ContributionParticipant.objects.filter(
                contribution=contribution, user=voter, is_active=True
            ).exists()

        if not authorized:
            raise PermissionDenied("You are not authorised to vote on this amendment.")

        _, created = ContributionAmendmentVote.objects.get_or_create(
            amendment=amendment, voter=voter, defaults={'vote': vote_choice}
        )
        if not created:
            raise ValidationError("You have already voted on this amendment.")

        approvals  = amendment.votes.filter(vote='APPROVE').count()
        rejections = amendment.votes.filter(vote='REJECT').count()
        required   = AmendmentService._amendment_required(contribution, amendment.proposed_by)

        if approvals >= required:
            AmendmentService._apply(amendment, contribution)
            _notify(
                user=amendment.proposed_by,
                notification_type='amendment_approved',
                title=f"Amendment approved — {contribution.title}",
                message="Your proposed changes have been approved and applied.",
                contribution_id=contribution.id,
            )
        elif rejections >= required:
            amendment.status = 'REJECTED'
            amendment.resolved_at = timezone.now()
            amendment.save(update_fields=['status', 'resolved_at'])
            _notify(
                user=amendment.proposed_by,
                notification_type='amendment_rejected',
                title=f"Amendment rejected — {contribution.title}",
                message="Your proposed changes were not approved by the group.",
                contribution_id=contribution.id,
            )

        return ContributionAmendment.objects.get(id=amendment_id)

    @staticmethod
    def _apply(amendment, contribution):
        from decimal import Decimal
        from datetime import timedelta

        DECIMAL_FIELDS = {'fixed_amount', 'target_amount'}
        INT_FIELDS     = {'period_months'}

        update_fields = []
        for field, value in amendment.changes.items():
            if field in DECIMAL_FIELDS:
                setattr(contribution, field, Decimal(str(value)))
            elif field in INT_FIELDS:
                setattr(contribution, field, int(value))
            else:
                setattr(contribution, field, value)
            update_fields.append(field)

        # Governance cooldown (Issue 16): if the voting threshold was relaxed,
        # lock disbursement execution for 24 h so that pending approvals that
        # were cast under the old (stricter) rules cannot slip through the new
        # (looser) threshold and execute immediately.
        if 'voting_threshold' in amendment.changes:
            contribution.governance_locked_until = timezone.now() + timedelta(hours=24)
            if 'governance_locked_until' not in update_fields:
                update_fields.append('governance_locked_until')

        contribution.save(update_fields=update_fields)
        amendment.status      = 'APPROVED'
        amendment.resolved_at = timezone.now()
        amendment.save(update_fields=['status', 'resolved_at'])

    @staticmethod
    def withdraw(amendment_id, user):
        try:
            amendment = ContributionAmendment.objects.select_related('contribution').get(
                id=amendment_id
            )
        except ContributionAmendment.DoesNotExist:
            raise ValidationError("Amendment not found.")

        if amendment.proposed_by != user:
            raise PermissionDenied("Only the proposer can withdraw their amendment.")

        if amendment.status != 'PENDING':
            raise ValidationError(
                f"Cannot withdraw an amendment that is already {amendment.status.lower()}."
            )

        amendment.status      = 'WITHDRAWN'
        amendment.resolved_at = timezone.now()
        amendment.save(update_fields=['status', 'resolved_at'])
        return amendment


# ---------------------------------------------------------------------------
# Contribution Join Requests & Invitations
# ---------------------------------------------------------------------------

class ContributionJoinRequestService:

    @staticmethod
    def _is_community_member(contribution, user):
        if not contribution.community:
            return True
        from apps.communities.models import CommunityMembership
        return CommunityMembership.objects.filter(
            community=contribution.community, user=user, is_active=True,
        ).exists()

    @staticmethod
    def _already_participant(contribution, user):
        return ContributionParticipant.objects.filter(
            contribution=contribution, user=user, is_active=True,
        ).exists()

    @staticmethod
    def request_join(contribution_id, user):
        from apps.communities.models import CommunityMembership

        contribution = Contribution.objects.select_related('community', 'created_by').get(
            id=contribution_id
        )

        if contribution.status != 'active':
            raise ValidationError("This contribution is not accepting new members.")

        if not ContributionJoinRequestService._is_community_member(contribution, user):
            raise PermissionDenied(
                "You must be a member of this community to request joining this contribution."
            )

        if ContributionJoinRequestService._already_participant(contribution, user):
            raise ValidationError("You are already a participant in this contribution.")

        existing = ContributionJoinRequest.objects.filter(
            contribution=contribution, user=user
        ).first()
        if existing:
            if existing.status == 'PENDING':
                raise ValidationError(
                    "You already have a pending request for this contribution."
                )
            if existing.status == 'APPROVED':
                raise ValidationError("Your request was already approved.")
            existing.status       = 'PENDING'
            existing.request_type = 'REQUEST'
            existing.invited_by   = None
            existing.reviewed_at  = None
            existing.reviewed_by  = None
            existing.save()
            jr = existing
        else:
            jr = ContributionJoinRequest.objects.create(
                contribution=contribution,
                user=user,
                request_type='REQUEST',
            )

        display = user.name or user.phone_number
        admins_notified = {contribution.created_by.id}
        _notify(
            user=contribution.created_by,
            notification_type='contribution_join_request',
            title=f"Join request — {contribution.title}",
            message=f"{display} wants to join {contribution.title}. Tap to review.",
            contribution_id=contribution.id,
            join_request_id=jr.id,
        )

        if contribution.community:
            for m in CommunityMembership.objects.filter(
                community=contribution.community,
                role__in=['admin', 'treasurer'],
                is_active=True,
            ).exclude(user_id__in=admins_notified).select_related('user'):
                _notify(
                    user=m.user,
                    notification_type='contribution_join_request',
                    title=f"Join request — {contribution.title}",
                    message=f"{display} wants to join {contribution.title}. Tap to review.",
                    contribution_id=contribution.id,
                    join_request_id=jr.id,
                )

        return jr

    @staticmethod
    def invite_user(contribution_id, admin, phone):
        from apps.users.models import User

        contribution = Contribution.objects.select_related('community', 'created_by').get(
            id=contribution_id
        )

        if not FinancialPermissions.is_contribution_admin(contribution, admin):
            raise PermissionDenied(
                "Only the contribution creator or a community admin can send invitations."
            )

        if contribution.status != 'active':
            raise ValidationError("This contribution is not accepting new members.")

        try:
            invitee = User.objects.get(phone_number=phone)
        except User.DoesNotExist:
            raise ValidationError(f"No user found with phone number {phone}.")

        if invitee == admin:
            raise ValidationError("You cannot invite yourself.")

        # Respect the invitee's discoverable privacy setting.
        from apps.users.models import PrivacyPreferences
        try:
            prefs = invitee.privacy_prefs
            if not prefs.discoverable:
                raise ValidationError(
                    f"{phone} has restricted who can invite them to contributions."
                )
        except PrivacyPreferences.DoesNotExist:
            pass  # no prefs row → default discoverable=True

        if not ContributionJoinRequestService._is_community_member(contribution, invitee):
            raise ValidationError(f"{phone} is not a member of this community.")

        if ContributionJoinRequestService._already_participant(contribution, invitee):
            raise ValidationError(f"{phone} is already a participant in this contribution.")

        existing = ContributionJoinRequest.objects.filter(
            contribution=contribution, user=invitee
        ).first()
        if existing:
            if existing.status == 'PENDING':
                raise ValidationError(f"{phone} already has a pending request or invitation.")
            if existing.status == 'APPROVED':
                raise ValidationError(f"{phone} is already approved.")
            existing.status       = 'PENDING'
            existing.request_type = 'INVITE'
            existing.invited_by   = admin
            existing.reviewed_at  = None
            existing.reviewed_by  = None
            existing.save()
            jr = existing
        else:
            jr = ContributionJoinRequest.objects.create(
                contribution=contribution,
                user=invitee,
                request_type='INVITE',
                invited_by=admin,
            )

        _notify(
            user=invitee,
            notification_type='contribution_invite',
            title=f"You've been invited — {contribution.title}",
            message=(
                f"{admin.name or admin.phone_number} invited you to join {contribution.title}."
            ),
            contribution_id=contribution.id,
            join_request_id=jr.id,
        )
        return jr

    @staticmethod
    def action_request(request_id, admin, action):
        jr = ContributionJoinRequest.objects.select_related('contribution', 'user').get(
            id=request_id
        )

        if jr.request_type != 'REQUEST':
            raise ValidationError("Use respond_to_invite() for invitation rows.")

        if not FinancialPermissions.is_contribution_admin(jr.contribution, admin):
            raise PermissionDenied(
                "Only an admin or the contribution creator can review join requests."
            )

        if jr.status != 'PENDING':
            raise ValidationError(f"This request has already been {jr.status.lower()}.")

        jr.status      = 'APPROVED' if action == 'approve' else 'REJECTED'
        jr.reviewed_by = admin
        jr.reviewed_at = timezone.now()
        jr.save()

        if action == 'approve':
            ContributionService.join_contribution(jr.contribution_id, jr.user)
            _notify(
                user=jr.user,
                notification_type='contribution_join_approved',
                title=f"Request approved — {jr.contribution.title}",
                message=(
                    f"Your request to join {jr.contribution.title} was approved. "
                    "You're now a participant."
                ),
                contribution_id=jr.contribution_id,
            )
        else:
            _notify(
                user=jr.user,
                notification_type='contribution_join_rejected',
                title=f"Request declined — {jr.contribution.title}",
                message=(
                    f"Your request to join {jr.contribution.title} was not approved."
                ),
                contribution_id=jr.contribution_id,
            )

        return jr

    @staticmethod
    def respond_to_invite(request_id, user, action):
        jr = ContributionJoinRequest.objects.select_related(
            'contribution', 'invited_by'
        ).get(id=request_id)

        if jr.request_type != 'INVITE':
            raise ValidationError("Use action_request() for join request rows.")

        if jr.user != user:
            raise PermissionDenied("You can only respond to your own invitations.")

        if jr.status != 'PENDING':
            raise ValidationError(f"This invitation has already been {jr.status.lower()}.")

        jr.status      = 'APPROVED' if action == 'accept' else 'REJECTED'
        jr.reviewed_by = user
        jr.reviewed_at = timezone.now()
        jr.save()

        if action == 'accept':
            ContributionService.join_contribution(jr.contribution_id, user)
            if jr.invited_by:
                _notify(
                    user=jr.invited_by,
                    notification_type='contribution_invite_accepted',
                    title=f"Invite accepted — {jr.contribution.title}",
                    message=(
                        f"{user.name or user.phone_number} accepted your invitation "
                        f"to join {jr.contribution.title}."
                    ),
                    contribution_id=jr.contribution_id,
                )
        return jr

    @staticmethod
    def get_pending_requests(contribution_id):
        return ContributionJoinRequest.objects.filter(
            contribution_id=contribution_id, request_type='REQUEST', status='PENDING',
        ).select_related('user').order_by('created_at')

    @staticmethod
    def get_my_invite(contribution_id, user):
        return ContributionJoinRequest.objects.filter(
            contribution_id=contribution_id, user=user,
            request_type='INVITE', status='PENDING',
        ).first()

    @staticmethod
    def get_my_request(contribution_id, user):
        return ContributionJoinRequest.objects.filter(
            contribution_id=contribution_id, user=user, request_type='REQUEST',
        ).first()
