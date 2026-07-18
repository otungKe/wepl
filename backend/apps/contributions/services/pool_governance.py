"""Maker-checker governance for collective-fund spend (ADR-0027).

Spending pool funds (an expense) or declaring a distribution moves *members'*
money, so it never executes on one admin's say-so: an admin *requests*, a second
admin *approves*, and only then does it post through the ledger. Mirrors the
disbursement governance pattern (quorum check up front to surface deadlock, a
distinct approver, execution on threshold). External income (money in) is benign
and bypasses this — it stays a direct admin action.
"""
from ._common import *  # shared imports + helpers (ADR-0013 view split)

from ..models import PoolActionRequest, PoolActionApproval
from .contribution import ContributionService

# One distinct admin checker beyond the maker. (Richer, threshold-configurable
# governance is a future refinement — see ADR-0027.)
REQUIRED_APPROVALS = 1


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

        amount = Decimal(str(amount))
        if amount <= 0:
            raise ValidationError("Amount must be greater than 0")
        if action not in PoolActionRequest.Action.values:
            raise ValidationError(f"Unknown action {action!r}.")
        if apportion not in ('pro_rata', 'per_capita'):
            raise ValidationError(f"Unknown apportion mode {apportion!r}.")

        contribution = Contribution.objects.select_for_update().get(id=contribution_id)
        require(admin_user, "contribution.admin", contribution,
                "Only a contribution admin can propose a collective-fund action.")

        # Funds must be available now (re-checked at execution too).
        if action == PoolActionRequest.Action.EXPENSE:
            if amount > fund_balance('contribution', contribution.id):
                raise ValidationError("Expense exceeds the pool balance.")
        else:  # DISTRIBUTION
            surplus = account_balance(_c.retained_surplus_account(fund_id=contribution.id))
            if amount > surplus:
                raise ValidationError("Distribution exceeds the retained surplus.")

        # Deadlock guard: a distinct admin must exist to approve (maker-checker).
        FinancialPermissions.assert_quorum_exists(
            contribution, 'admins', admin_user,
            action="approve this collective-fund action")

        return PoolActionRequest.objects.create(
            contribution=contribution, action=action, amount=amount,
            apportion=apportion, memo=memo, requested_by=admin_user)

    @staticmethod
    @transaction.atomic
    def approve(admin_user, request_id):
        """A second admin approves; on reaching the threshold the action executes
        through the ledger. The maker cannot approve their own request."""
        from apps.core.policy import require

        req = PoolActionRequest.objects.select_for_update().get(
            id=request_id, status=PoolActionRequest.Status.PENDING)
        require(admin_user, "contribution.admin", req.contribution,
                "Only a contribution admin can approve a collective-fund action.")
        if req.requested_by_id == admin_user.id:
            raise PermissionDenied("You cannot approve your own request.")

        _, created = PoolActionApproval.objects.get_or_create(request=req, approver=admin_user)
        if not created:
            raise ValidationError("You have already approved this request.")

        if req.approvals.count() >= REQUIRED_APPROVALS:
            PoolGovernanceService._execute(req, decided_by=admin_user)
        return req

    @staticmethod
    def _execute(req, *, decided_by):
        """Run the approved action through the ledger and record the result. The
        underlying services re-validate funds and re-check the admin gate."""
        if req.action == PoolActionRequest.Action.EXPENSE:
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
        """A second admin rejects the request (the maker cannot self-reject)."""
        from apps.core.policy import require
        req = PoolActionRequest.objects.select_for_update().get(
            id=request_id, status=PoolActionRequest.Status.PENDING)
        require(admin_user, "contribution.admin", req.contribution,
                "Only a contribution admin can reject a collective-fund action.")
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
