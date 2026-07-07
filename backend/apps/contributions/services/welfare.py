from ._common import *  # shared imports + helpers (ADR-0013 split)


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

        # Key anchored to the M-Pesa receipt (externally-assigned, immutable);
        # retries with the same receipt are no-ops via post_journal idempotency.
        idem_key = f"welfare-contrib-{fund_id}-{user.id}-{mpesa_receipt}"
        ft, _ = create_fin_transaction(
            idempotency_key=idem_key,
            op_type=FinancialTransaction.OpType.WELFARE_CONTRIBUTION,
            amount=Decimal(str(amount)),
            initiated_by=user,
            welfare_fund=fund,
            initial_state=FinancialTransaction.State.SUCCESS,
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

        # Amount is sensitive — keep the contributor's welfare payment private.
        ActivityService.record(
            actor=user,
            verb='welfare_contribution',
            params={"amount": str(amount)},
            visibility=Activity.Visibility.PRIVATE,
        )
        fund.refresh_from_db()
        return fund

    @staticmethod
    @transaction.atomic
    def submit_claim(fund_id, user, amount_requested, reason):
        AccessPolicy.gate(user, "Verify your identity to submit a welfare claim.")
        fund   = WelfareFund.objects.select_for_update().get(id=fund_id)
        amount = Decimal(str(amount_requested))

        # Lifecycle + Section B cooling-off checks
        if fund.community:
            from apps.communities.services import check_cooling_off, require_active_community
            require_active_community(fund.community, 'submit a welfare claim')
            check_cooling_off(user, fund.community, 'welfare_claim')

        if WelfareClaim.objects.filter(fund=fund, claimant=user, status='PENDING').exists():
            raise ValidationError(
                "You already have a pending claim. "
                "Wait for it to be reviewed before submitting another."
            )
        welfare_bal = fund_balance('welfare', fund.id)
        if amount > welfare_bal:
            raise ValidationError(
                f"Claim amount exceeds the current fund balance of KES {welfare_bal:,.0f}."
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

        require(admin_user, "community.finance.manage", claim.fund.community,
                "Only community admins can approve welfare claims.")

        WelfareService._disburse(claim)
        AuditService.log(
            "welfare.claim_approved", actor=admin_user, target=claim,
            tenant=getattr(claim.fund.community, "tenant_id", None),
            metadata={"amount": str(claim.amount_requested), "claimant_id": claim.claimant_id},
        )
        return WelfareClaim.objects.get(id=claim_id)

    @staticmethod
    def reject_claim(claim_id, admin_user):
        claim = WelfareClaim.objects.get(id=claim_id, status='PENDING')

        if claim.claimant == admin_user:
            raise PermissionDenied("You cannot reject your own welfare claim.")

        require(admin_user, "community.finance.manage", claim.fund.community,
                "Only community admins can reject welfare claims.")

        claim.transition_to('REJECTED')
        AuditService.log(
            "welfare.claim_rejected", actor=admin_user, target=claim,
            tenant=getattr(claim.fund.community, "tenant_id", None),
            metadata={"amount": str(claim.amount_requested), "claimant_id": claim.claimant_id},
        )
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
        if fund_balance('welfare', fund.id) < claim.amount_requested:
            raise ValidationError("Insufficient welfare fund balance.")

        # ── Reserve funds: post the payout journal (cash leaves on B2C success) ─
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
