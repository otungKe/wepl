from ._common import *  # shared imports + helpers (ADR-0013 split)


class DisbursementService:

    @staticmethod
    @transaction.atomic
    def create_request(contribution_id, user, amount, reason, recipient_phone):
        contribution = Contribution.objects.select_for_update().get(id=contribution_id)

        require(user, "contribution.participate", contribution,
                "You must be an active participant.")

        # Balance check — pool balance from the ledger (contribution row is locked
        # above, serialising concurrent disbursements on this contribution).
        if Decimal(str(amount)) > fund_balance('contribution', contribution.id):
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

        # Authorization — threshold-aware voting eligibility (ADR-0009 policy)
        require(voter, "contribution.vote_disbursement", contribution,
                "You are not authorised to vote on this request.")

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

        if fund_balance('contribution', contribution.id) < req.amount:
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

        # ── WITHDRAWAL record (transaction history) ───────────────────────────
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
