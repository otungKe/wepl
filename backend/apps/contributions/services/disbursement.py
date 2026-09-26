from ._common import *  # shared imports + helpers (ADR-0013 split)
from .. import governance
from .contribution import _share_allocations


class DisbursementService:

    @staticmethod
    @transaction.atomic
    def create_request(contribution_id, user, amount, reason, recipient_phone):
        AccessPolicy.gate(user, "Verify your identity to request a payout.")
        contribution = Contribution.objects.select_for_update().get(id=contribution_id)

        require(user, "contribution.participate", contribution,
                "You must be an active participant.")

        if contribution.community:
            from apps.communities.services import require_active_community
            require_active_community(contribution.community, 'request a payout')

        # Balance check — cash the pool holds, from the ledger (contribution row
        # is locked above, serialising concurrent disbursements on it).
        if Decimal(str(amount)) > pool_cash(contribution.id):
            raise ValidationError("Amount exceeds current pool balance.")

        # Quorum check: ensure at least one eligible voter exists excluding the requester.
        # Catches dynamic deadlocks (e.g. last admin left after contribution was created).
        from apps.contributions.permissions import FinancialPermissions
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
        AccessPolicy.gate(voter, "Verify your identity to vote on a payout.")
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

        # Authorization — threshold-aware voting eligibility (ADR-0009 policy)
        require(voter, "contribution.vote_disbursement", contribution,
                "You are not authorised to vote on this request.")

        governance.record_vote(req.votes, voter, vote_choice,
                               already="You have already voted on this disbursement request.")
        outcome = governance.tally(req.votes, contribution.required_approvals()).outcome

        if outcome == governance.PASSED:
            req.transition_to('APPROVED')
            DisbursementService._schedule_execution(req)

        elif outcome == governance.FAILED:
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

    # ── Exit settlement (ADR-0027 §0.4) ──────────────────────────────────────

    @staticmethod
    def _open_advances(contribution, user):
        return EmergencyAdvance.objects.filter(
            contribution=contribution, borrower=user, status='DISBURSED')

    @staticmethod
    def exit_quote(contribution, user) -> dict:
        """What a leaving member would be paid now: their share less what they
        still owe on advances from this pool (principal and interest)."""
        share = member_fund_balance(user, 'contribution', contribution.id)
        owed = sum(
            (a.balance_due for a in DisbursementService._open_advances(contribution, user)),
            Decimal('0'))
        return {'share': share, 'owed': owed, 'payout': share - owed}

    @staticmethod
    @transaction.atomic
    def request_exit(contribution_id, user, recipient_phone=None):
        """A member asks for their share back on leaving. The group votes it like
        any payout and must decide within ``EXIT_DECISION_DAYS``; nothing moves
        until it is approved, and a refused member is paid at wind-up."""
        AccessPolicy.gate(user, "Verify your identity to request your share.")
        contribution = Contribution.objects.select_for_update().get(id=contribution_id)

        # A member who has already left keeps their share and may still ask for
        # it, so this is membership of the pool, not active participation.
        if not ContributionParticipant.objects.filter(
                contribution=contribution, user=user).exists():
            raise PermissionDenied("You are not a member of this contribution.")
        if contribution.contribution_type == 'ROSCA':
            raise ValidationError(
                "A rotating group settles through its rotation, not an exit payout.")

        if DisbursementRequest.objects.filter(
                contribution=contribution, requested_by=user,
                kind=DisbursementRequest.KIND_EXIT,
                status__in=('PENDING', 'APPROVED')).exists():
            raise ValidationError("You already have an exit request open.")

        quote = DisbursementService.exit_quote(contribution, user)
        if quote['payout'] <= 0:
            raise ValidationError(
                "You have no share to pay out"
                + (" after what you owe on your advance." if quote['owed'] > 0 else "."))

        from apps.contributions.permissions import FinancialPermissions
        FinancialPermissions.assert_quorum_exists(
            contribution, contribution.voting_threshold, user,
            action="submit this exit request",
        )

        req = DisbursementRequest.objects.create(
            contribution=contribution,
            requested_by=user,
            amount=quote['payout'],
            reason="Exit settlement: share paid out on leaving",
            recipient_phone=recipient_phone or user.phone_number,
            kind=DisbursementRequest.KIND_EXIT,
            decide_by=timezone.now() + timedelta(days=DisbursementRequest.EXIT_DECISION_DAYS),
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
                    title=f"Exit request — {contribution.title}",
                    message=(
                        f"{_dn(user)} is leaving and asks for their share of "
                        f"KES {quote['payout']:,.0f}. The group must decide within "
                        f"{DisbursementRequest.EXIT_DECISION_DAYS} days."
                    ),
                    contribution_id=contribution.id,
                    join_request_id=req.id,
                )
        return req

    @staticmethod
    def _execute_exit(req: 'DisbursementRequest', contribution) -> None:
        """Settle an approved exit: set any unpaid advance off against the
        member's share, pay out the rest of the share, and end their membership.
        Runs inside ``_schedule_execution``'s transaction."""
        DisbursementService._set_off_advances(contribution, req.requested_by, key=f"exit-setoff-{req.id}")
        DisbursementService._pay_out_share(req, contribution)

    @staticmethod
    def _set_off_advances(contribution, member, *, key) -> None:
        """Take what ``member`` still owes on advances from this pool out of
        their share, as a repayment would, so each advance reads as repaid and
        the pool's lent cash is no longer counted as out on loan."""
        for advance in DisbursementService._open_advances(contribution, member).select_for_update():
            owed = advance.balance_due
            if owed <= 0:
                continue
            outstanding = max(account_balance(
                _coa.member_receivable_account(user=member, fund_id=advance.id)), Decimal('0'))
            principal = min(owed, outstanding)
            interest = owed - principal
            ft, _ = create_fin_transaction(
                idempotency_key=f"{key}-{advance.id}",
                op_type=FinancialTransaction.OpType.ADVANCE_REPAYMENT,
                amount=owed,
                initiated_by=member,
                contribution=contribution,
                context_type='emergency_advance',
                context_id=advance.id,
                initial_state=FinancialTransaction.State.SUCCESS,
            )
            post_journal(
                idempotency_key=f"je-{key}-{advance.id}",
                op_type=_pm.Op.ADVANCE_REPAYMENT,
                lines=_pm.advance_setoff_lines(
                    member=member, advance_id=advance.id, pool_id=contribution.id,
                    principal=Money(str(principal)), interest=Money(str(interest)),
                ),
                narration=f"Advance #{advance.id} set off against share on exit",
                financial_transaction=ft,
                created_by=member,
            )
            advance.transition_to('REPAID')

    @staticmethod
    def _pay_out_share(req: 'DisbursementRequest', contribution) -> None:
        """Pay ``req.requested_by`` their whole share as it stands now, not as
        quoted when the request was made — group spending or income since then
        is theirs too — and end their membership."""
        member = req.requested_by
        share = member_fund_balance(member, 'contribution', contribution.id)
        if share <= 0:
            raise ValidationError("The member has no share left to pay out.")
        if pool_cash(contribution.id) < share:
            raise ValidationError("Insufficient pool balance at execution time.")
        if share != req.amount:
            DisbursementRequest.objects.filter(pk=req.pk).update(amount=share)
            req.amount = share

        idem_key = f"disb-exec-{req.id}"
        ft, created = create_fin_transaction(
            idempotency_key=idem_key,
            op_type=FinancialTransaction.OpType.DISBURSEMENT,
            amount=share,
            initiated_by=member,
            recipient_phone=req.recipient_phone,
            contribution=contribution,
            context_type='disbursement_request',
            context_id=req.id,
        )
        if not created and ft.state in (
            FinancialTransaction.State.SUCCESS,
            FinancialTransaction.State.PROCESSING,
        ):
            return

        # Unlike a group payout this is the member's own claim, so only their
        # share is drawn down. The request is kept so a failed payout resets it
        # to APPROVED and restores the share, exactly as for any payout.
        post_journal(
            idempotency_key=f"je-{idem_key}",
            op_type=_pm.Op.DISBURSEMENT,
            lines=_pm.disbursement_lines(
                member=member, fund_type='contribution', fund_id=contribution.id,
                amount=Money(str(share)),
            ),
            narration=req.reason[:120],
            financial_transaction=ft,
            created_by=member,
        )

        ContributionParticipant.objects.filter(
            contribution=contribution, user=member).update(is_active=False)

        winding_up = req.kind == DisbursementRequest.KIND_WINDUP
        AuditService.log(
            "contribution.wind_up_paid" if winding_up else "contribution.exit_settled",
            actor=member, target=req,
            tenant=getattr(contribution.community, "tenant_id", None),
            metadata={"amount": str(share), "contribution_id": contribution.id},
        )
        _notify(
            user=member,
            notification_type='disbursement_executed',
            title=f"{contribution.title} is wound up" if winding_up else "Exit approved",
            message=(
                f"Your share of KES {share:,.2f} from '{contribution.title}' is "
                f"being sent to {req.recipient_phone}."
            ),
            contribution_id=contribution.id,
        )

        ft_id = ft.id

        def _dispatch():
            from apps.payments.payouts import execute_payout
            from apps.core.dispatch import safe_enqueue
            safe_enqueue(execute_payout, ft_id, critical=True)

        transaction.on_commit(_dispatch)
        req.transition_to('EXECUTED', executed_at=timezone.now())

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

        if req.kind == DisbursementRequest.KIND_EXIT:
            DisbursementService._execute_exit(req, contribution)
            return

        if pool_cash(contribution.id) < req.amount:
            raise ValidationError("Insufficient pool balance at execution time.")

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

        # Double-entry posting (P0-05): reserve funds out of the pool. The group
        # voted this spend, so it is the group's cost: every funded member's
        # share bears its pro-rata part, not the requester's alone (ADR-0027
        # §0.1). A failed payout reverses the whole journal line for line.
        post_journal(
            idempotency_key=f"je-{idem_key}",
            op_type=_pm.Op.DISBURSEMENT,
            lines=_pm.pool_expense_lines(
                fund_type='contribution', fund_id=contribution.id,
                allocations=_share_allocations(contribution.id, req.amount),
            ),
            narration=f"Disbursement: {req.reason[:120]}",
            financial_transaction=ft,
            created_by=req.requested_by,
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
            from apps.payments.payouts import execute_payout
            from apps.core.dispatch import safe_enqueue
            safe_enqueue(execute_payout, ft_id, critical=True)

        transaction.on_commit(_dispatch)

        # Mark FT as PROCESSING once we've queued the Celery task
        # (the task itself will transition to SUCCESS/FAILED via B2C callback)
        req.transition_to('EXECUTED', executed_at=timezone.now())


# ---------------------------------------------------------------------------
# Welfare Fund
# ---------------------------------------------------------------------------
