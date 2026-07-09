from ._common import *  # shared imports + helpers (ADR-0013 split)


class EmergencyAdvanceService:

    MAX_ADVANCE_RATIO = Decimal('0.80')

    @staticmethod
    def request_advance(contribution_id, user, amount, interest_rate, repayment_due):
        # Tier-1 (KYC-approved) gate — centralized (ADR-0022).
        AccessPolicy.require_tier1(
            user, "Your identity verification must be approved before requesting an advance.")

        contribution = Contribution.objects.get(id=contribution_id)

        require(user, "contribution.participate", contribution,
                "You must be an active participant.")

        # Lifecycle + Section B cooling-off checks
        if contribution.community:
            from apps.communities.services import check_cooling_off, require_active_community
            require_active_community(contribution.community, 'request an advance')
            check_cooling_off(user, contribution.community, 'emergency_advance')

        # Eligibility from the double-entry ledger: the member's own contribution
        # sub-ledger balance (what the pool owes them).
        member_acct = _coa.member_fund_account(
            user=user, fund_type='contribution', fund_id=contribution.id)
        member_total = account_balance(member_acct)

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

        require(admin_user, "contribution.admin", contribution,
                "Only admins/treasurers can approve advances.")

        # Check pool has enough funds (ledger-derived)
        if fund_balance('contribution', contribution.id) < advance.amount:
            raise ValidationError("Insufficient pool balance to cover this advance.")

        # ── Reserve funds: post the payout journal (cash leaves on B2C success) ─
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

        ContributionTransaction.objects.create(
            contribution=contribution,
            user=advance.borrower,
            amount=advance.amount,
            transaction_type='ADVANCE',
            note=f"Emergency advance #{advance.id}",
            financial_transaction=ft,
        )

        advance.transition_to('DISBURSED')

        AuditService.log(
            "advance.approved", actor=admin_user, target=advance,
            tenant=getattr(contribution.community, "tenant_id", None),
            metadata={"amount": str(advance.amount), "borrower_id": advance.borrower_id,
                      "contribution_id": contribution.id},
        )

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

        require(admin_user, "contribution.admin", contribution,
                "Only admins/treasurers can reject advances.")

        advance.transition_to('REJECTED')
        AuditService.log(
            "advance.rejected", actor=admin_user, target=advance,
            tenant=getattr(contribution.community, "tenant_id", None),
            metadata={"amount": str(advance.amount), "borrower_id": advance.borrower_id,
                      "contribution_id": contribution.id},
        )
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
        # Double-entry posting (P0-06): split the repayment into principal (clears
        # the receivable) and interest (income). Outstanding principal is the AR
        # sub-ledger balance, so the principal portion never over-clears it.
        ar_acct = _coa.member_receivable_account(user=user, fund_id=advance.id)
        outstanding = account_balance(ar_acct)
        principal_portion = min(Decimal(str(amount)), max(outstanding, Decimal('0')))
        interest_portion = Decimal(str(amount)) - principal_portion
        post_journal(
            idempotency_key=f"je-{idem_key}",
            op_type=_pm.Op.ADVANCE_REPAYMENT,
            lines=_pm.advance_repayment_lines(
                member=user, advance_id=advance.id,
                principal=Money(str(principal_portion)),
                interest=Money(str(interest_portion)),
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
            financial_transaction=ft,
        )

        return advance


# ---------------------------------------------------------------------------
# Standing Orders
# ---------------------------------------------------------------------------
