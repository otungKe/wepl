"""Maker-checker governance for collective-fund spend (ADR-0027).

Spending pool funds (an expense), declaring a distribution or winding the pool
up moves the group's money, so it never executes on one admin's say-so: an admin *requests*, and it
posts through the ledger only once the group has approved it under its own
voting threshold — the same rule a voted payout follows (ADR-0027 §0.1). Quorum
is checked up front to surface deadlock, and the maker never approves. External income (money in) is benign
and bypasses this — it stays a direct admin action.
"""
from ._common import *  # shared imports + helpers (ADR-0013 view split)

from ..models import PoolActionRequest, PoolActionApproval
from .contribution import ContributionService
from .wind_up import WindUpService

class PoolGovernanceService:

    @staticmethod
    @transaction.atomic
    def request(admin_user, contribution_id, *, action, amount,
                apportion='pro_rata', memo=''):
        """An admin proposes a collective-fund action. Validated up front (funds
        available, a second admin exists to approve) so deadlock/overspend surface
        immediately, then held PENDING for a checker."""
        from apps.core.policy import can, require
        from apps.ledger.balances import account_balance
        from apps.ledger import coa as _c

        if action not in PoolActionRequest.Action.values:
            raise ValidationError(f"Unknown action {action!r}.")
        if apportion not in ('pro_rata', 'per_capita'):
            raise ValidationError(f"Unknown apportion mode {apportion!r}.")

        contribution = Contribution.objects.select_for_update().get(id=contribution_id)
        require(admin_user, "contribution.admin", contribution,
                "Only a contribution admin can propose a collective-fund action.")

        if action == PoolActionRequest.Action.WIND_UP:
            # A wind-up pays out everything, so its amount is not the
            # proposer's to choose: it records what the pool holds now, and
            # execution pays what it holds then.
            WindUpService.check(contribution)
            amount = WindUpService.total(contribution)
            if PoolActionRequest.objects.filter(
                    contribution=contribution, action=action,
                    status=PoolActionRequest.Status.PENDING).exists():
                raise ValidationError("A wind-up is already awaiting approval.")

        amount = Decimal(str(amount))
        if amount <= 0:
            raise ValidationError("Amount must be greater than 0")

        # Funds must be available now (re-checked at execution too).
        if action == PoolActionRequest.Action.WIND_UP:
            pass
        elif action == PoolActionRequest.Action.EXPENSE:
            if amount > pool_cash(contribution.id):
                raise ValidationError("Expense exceeds the pool balance.")
        else:  # DISTRIBUTION
            surplus = account_balance(_c.retained_surplus_account(fund_id=contribution.id))
            if amount > surplus:
                raise ValidationError("Distribution exceeds the retained surplus.")

        # Deadlock guard: someone other than the maker must be able to approve
        # under the group's own voting threshold — the same one a payout uses.
        FinancialPermissions.assert_quorum_exists(
            contribution, contribution.voting_threshold, admin_user,
            action="approve this collective-fund action")

        return PoolActionRequest.objects.create(
            contribution=contribution, action=action, amount=amount,
            apportion=apportion, memo=memo, requested_by=admin_user)

    @staticmethod
    @transaction.atomic
    def approve(admin_user, request_id):
        """Spending group money is a group decision (ADR-0027 §0.1): approval
        follows the contribution's voting threshold exactly as a voted payout
        does — who may vote (``contribution.vote_disbursement``) and how many
        approvals it takes (``required_approvals``). On reaching it the action
        executes through the ledger. The maker cannot approve their own request.
        """
        from apps.core.policy import require

        req = PoolActionRequest.objects.select_for_update().get(
            id=request_id, status=PoolActionRequest.Status.PENDING)
        contribution = req.contribution
        require(admin_user, "contribution.vote_disbursement", contribution,
                "You are not authorised to approve this collective-fund action.")
        if req.requested_by_id == admin_user.id:
            raise PermissionDenied("You cannot approve your own request.")

        _, created = PoolActionApproval.objects.get_or_create(request=req, approver=admin_user)
        if not created:
            raise ValidationError("You have already approved this request.")

        if req.approvals.count() >= contribution.required_approvals():
            # Same 24 h cooldown as a payout after the threshold was changed.
            if (contribution.governance_locked_until
                    and contribution.governance_locked_until > timezone.now()):
                raise ValidationError(
                    "Governance rules were recently changed. Spending is locked "
                    "until the cooldown ends.")
            PoolGovernanceService._execute(req, decided_by=admin_user)
        return req

    @staticmethod
    def _execute(req, *, decided_by):
        """Run the approved action through the ledger and record the result. The
        underlying services re-validate funds and re-check the admin gate."""
        if req.action == PoolActionRequest.Action.WIND_UP:
            WindUpService.execute(req)
            ft = None
        elif req.action == PoolActionRequest.Action.EXPENSE:
            ft = ContributionService.record_pool_expense(
                req.requested_by, req.contribution_id, req.amount,
                apportion=req.apportion, reason=req.memo)
        else:
            ft = ContributionService.declare_distribution(
                req.requested_by, req.contribution_id, req.amount,
                apportion=req.apportion, reason=req.memo)
        req.status = PoolActionRequest.Status.EXECUTED
        req.decided_by = decided_by
        req.financial_transaction = ft
        req.save(update_fields=['status', 'decided_by', 'financial_transaction', 'updated_at'])
        return ft

    @staticmethod
    @transaction.atomic
    def reject(admin_user, request_id, note=''):
        """An eligible voter rejects the request (the maker cannot self-reject)."""
        from apps.core.policy import require
        req = PoolActionRequest.objects.select_for_update().get(
            id=request_id, status=PoolActionRequest.Status.PENDING)
        require(admin_user, "contribution.vote_disbursement", req.contribution,
                "You are not authorised to reject this collective-fund action.")
        if req.requested_by_id == admin_user.id:
            raise PermissionDenied("You cannot reject your own request — cancel it instead.")
        req.status = PoolActionRequest.Status.REJECTED
        req.decided_by = admin_user
        req.decision_note = note[:255]
        req.save(update_fields=['status', 'decided_by', 'decision_note', 'updated_at'])
        return req

    @staticmethod
    @transaction.atomic
    def cancel(user, request_id):
        """The maker withdraws their own still-pending request."""
        req = PoolActionRequest.objects.select_for_update().get(
            id=request_id, status=PoolActionRequest.Status.PENDING)
        if req.requested_by_id != user.id:
            raise PermissionDenied("Only the requester can cancel this request.")
        req.status = PoolActionRequest.Status.CANCELLED
        req.save(update_fields=['status', 'updated_at'])
        return req
