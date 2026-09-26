"""Winding up a pool: the group decides to end it and everything is paid out
(ADR-0027 §0.1, §0.4).

A wind-up is proposed and approved through ``PoolGovernanceService`` like any
other spend of group money, under the group's voting threshold. Once approved:

1. Pending requests on the pool are cancelled and pending advances refused.
2. Every unpaid advance is set off against its borrower's share.
3. The retained surplus (advance interest, outside income) is shared out
   pro-rata to the members' shares.
4. Each member with a share is paid it, through a per-member
   ``DisbursementRequest`` so the B2C payout, its settlement and a failed
   payout's reset work exactly as they do for an exit.
5. Every participant is made inactive and the contribution closed.

A member the group refused an exit to is paid here at the latest. ROSCAs are
out of scope: they settle through their rotation.
"""
from ._common import *  # shared imports + helpers (ADR-0013 split)
from .contribution import _share_allocations
from .disbursement import DisbursementService


class WindUpService:

    @staticmethod
    def total(contribution) -> Decimal:
        """What a wind-up would pay out now: every share plus the surplus."""
        surplus = account_balance(_coa.retained_surplus_account(fund_id=contribution.id))
        return fund_balance('contribution', contribution.id) + surplus

    @staticmethod
    def check(contribution) -> None:
        """Refuse a wind-up that could not pay everyone in full."""
        from apps.ledger.balances import fund_member_balances
        if contribution.contribution_type == 'ROSCA':
            raise ValidationError(
                "A rotating group settles through its rotation, not a wind-up.")
        if fund_member_balances('contribution', contribution.id).get(None, Decimal('0')):
            raise ValidationError(
                "An organization holds a position in this pool; settle it before winding up.")
        for advance in EmergencyAdvance.objects.filter(
                contribution=contribution, status='DISBURSED').select_related('borrower'):
            share = member_fund_balance(advance.borrower, 'contribution', contribution.id)
            if advance.balance_due > share:
                raise ValidationError(
                    f"{_dn(advance.borrower)} owes KES {advance.balance_due:,.2f} on an "
                    f"advance, more than their share. Collect it before winding up.")

    @staticmethod
    def execute(action_req) -> None:
        """Run an approved wind-up. Called inside the approval's transaction."""
        contribution = Contribution.objects.select_for_update().get(id=action_req.contribution_id)
        WindUpService.check(contribution)

        # 1. Nothing else may move the pool's money once it is being wound up.
        for pending in DisbursementRequest.objects.filter(
                contribution=contribution, status='PENDING').select_for_update():
            pending.transition_to('CANCELLED')
        for advance in EmergencyAdvance.objects.filter(
                contribution=contribution, status='PENDING').select_for_update():
            advance.transition_to('REJECTED')
        from ..models import PoolActionRequest
        PoolActionRequest.objects.filter(
            contribution=contribution, status=PoolActionRequest.Status.PENDING,
        ).exclude(pk=action_req.pk).update(status=PoolActionRequest.Status.CANCELLED)

        # 2. Debts come out of the borrowers' shares.
        borrowers = {a.borrower for a in EmergencyAdvance.objects.filter(
            contribution=contribution, status='DISBURSED').select_related('borrower')}
        for member in borrowers:
            DisbursementService._set_off_advances(
                contribution, member, key=f"windup-setoff-{action_req.id}-{member.id}")

        # 3. The group's surplus is shared out by share, so it is paid below.
        surplus = account_balance(_coa.retained_surplus_account(fund_id=contribution.id))
        if surplus > 0:
            post_journal(
                idempotency_key=f"je-windup-surplus-{action_req.id}",
                op_type=_pm.Op.SURPLUS_DISTRIBUTION,
                lines=_pm.distribute_surplus_lines(
                    fund_id=contribution.id,
                    allocations=_share_allocations(contribution.id, surplus),
                ),
                narration=f"Wind-up: surplus shared out — {contribution.title}"[:120],
                created_by=action_req.requested_by,
            )

        # 4. Pay each member their share.
        from apps.ledger.balances import fund_member_balances
        from django.contrib.auth import get_user_model
        shares = {uid: bal for uid, bal
                  in fund_member_balances('contribution', contribution.id).items()
                  if uid is not None and bal > 0}
        for member in get_user_model().objects.filter(id__in=shares).order_by('id'):
            req = DisbursementRequest.objects.create(
                contribution=contribution,
                requested_by=member,
                amount=shares[member.id],
                reason=f"Wind-up: share of {contribution.title} paid out"[:255],
                recipient_phone=member.phone_number,
                kind=DisbursementRequest.KIND_WINDUP,
            )
            req.transition_to('APPROVED')
            DisbursementService._pay_out_share(req, contribution)

        # 5. The pool is closed.
        ContributionParticipant.objects.filter(contribution=contribution).update(is_active=False)
        contribution.status = 'closed'
        contribution.is_active = False
        contribution.save(update_fields=['status', 'is_active'])
        AuditService.log(
            "contribution.wound_up", actor=action_req.requested_by, target=contribution,
            tenant=getattr(contribution.community, "tenant_id", None),
            metadata={"members_paid": len(shares), "action_request_id": action_req.id},
        )
