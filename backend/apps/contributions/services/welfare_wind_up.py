"""Winding up a welfare fund (ADR-0027 §0.2).

Premiums are transfers: nobody holds a welfare share, so a wind-up does not
return what each member paid. What is left is split **per head among the
members who are paid up** at that point, whatever each paid in.

Paid up means every month's premium paid to date: a member's premiums into this
fund, read from the journal, cover ``monthly_contribution`` for every calendar
month from when their cover started (the later of the fund's creation and the
start of their current membership) up to and including this one. A fund with no
monthly premium set treats every active member as paid up.

One admin or treasurer proposes the wind-up and a different one approves it,
the same authority that decides claims, held to two people because it empties
the fund. On approval each paid-up member is paid their share by B2C and the
fund is closed to new premiums and claims.
"""
from django.db.models import Sum

from ._common import *  # shared imports + helpers (ADR-0013 split)
from .contribution import _apportion_amount
from ..models import WelfareWindUp, WelfareWindUpPayout


def _months_due(start, now) -> int:
    """Calendar months from ``start``'s month to ``now``'s, both included."""
    return max(0, (now.year - start.year) * 12 + now.month - start.month + 1)


class WelfareWindUpService:

    @staticmethod
    def premiums_paid(fund) -> dict:
        """{user_id: premiums paid into ``fund``}, from the premium journals.

        A premium credits the fund's pool account under ``WELFARE_CONTRIBUTION``
        (``posting_map.welfare_contribution_lines``); who paid is the journal's
        transaction's ``initiated_by``. Signed (credit − debit) and including
        the premium's reversal journal, so a reversed premium does not count."""
        from django.db.models import Case, DecimalField, F, When
        from apps.ledger.models import JournalLine
        pool = _coa.pool_account(fund_type='welfare', fund_id=fund.id)
        op = _pm.Op.WELFARE_CONTRIBUTION
        rows = (
            JournalLine.objects
            .filter(
                account=pool,
                journal__op_type__in=(op, f"REVERSAL_{op}"),
                journal__financial_transaction__welfare_fund_id=fund.id,
            )
            .values('journal__financial_transaction__initiated_by')
            .annotate(total=Sum(Case(
                When(direction=JournalLine.Direction.CREDIT, then=F('amount')),
                default=-F('amount'), output_field=DecimalField())))
        )
        return {r['journal__financial_transaction__initiated_by']: r['total'] for r in rows}

    @staticmethod
    def paid_up_members(fund, now=None) -> list:
        """The active community members who are paid up now, ordered by id."""
        from apps.communities.models import CommunityMembership
        now = now or timezone.now()
        memberships = (
            CommunityMembership.objects
            .filter(community=fund.community, is_active=True)
            .select_related('user').order_by('user_id')
        )
        premium = fund.monthly_contribution or Decimal('0')
        if premium <= 0:
            return [m.user for m in memberships]
        paid = WelfareWindUpService.premiums_paid(fund)
        members = []
        for m in memberships:
            start = max(fund.created_at, m.membership_start)
            if paid.get(m.user_id, Decimal('0')) >= premium * _months_due(start, now):
                members.append(m.user)
        return members

    @staticmethod
    def preview(fund) -> dict:
        """What a wind-up would pay now, without moving anything."""
        leftover = fund_balance('welfare', fund.id)
        members = WelfareWindUpService.paid_up_members(fund)
        shares = (_apportion_amount(leftover, [(u.id, Decimal('1')) for u in members])
                  if members and leftover > 0 else {})
        return {
            'balance': leftover,
            'paid_up_members': len(members),
            'per_head': max(shares.values()) if shares else Decimal('0'),
        }

    @staticmethod
    def _check(fund) -> None:
        if fund.closed_at:
            raise ValidationError("This welfare fund has already been wound up.")
        if fund.community is None:
            raise ValidationError("Only a community's welfare fund can be wound up.")
        if WelfareClaim.objects.filter(fund=fund, status__in=('PENDING', 'APPROVED')).exists():
            raise ValidationError("Decide the open welfare claims before winding up the fund.")
        if (fund_balance('welfare', fund.id) > 0
                and not WelfareWindUpService.paid_up_members(fund)):
            raise ValidationError(
                "No member is paid up, so there is nobody to share the fund between.")

    @staticmethod
    @transaction.atomic
    def request(user, fund_id, memo=''):
        fund = WelfareFund.objects.select_for_update().get(id=fund_id)
        if fund.community is not None:
            require(user, "community.finance.manage", fund.community,
                    "Only community admins can propose winding up the welfare fund.")
        WelfareWindUpService._check(fund)
        if WelfareWindUp.objects.filter(fund=fund, status=WelfareWindUp.Status.PENDING).exists():
            raise ValidationError("A wind-up is already awaiting approval.")
        return WelfareWindUp.objects.create(
            fund=fund, requested_by=user, memo=memo[:255],
            amount=fund_balance('welfare', fund.id))

    @staticmethod
    @transaction.atomic
    def approve(user, wind_up_id):
        wind_up = WelfareWindUp.objects.select_for_update().get(
            id=wind_up_id, status=WelfareWindUp.Status.PENDING)
        require(user, "community.finance.manage", wind_up.fund.community,
                "Only community admins can approve winding up the welfare fund.")
        if wind_up.requested_by_id == user.id:
            raise PermissionDenied("You cannot approve your own wind-up proposal.")
        WelfareWindUpService._execute(wind_up, decided_by=user)
        return wind_up

    @staticmethod
    @transaction.atomic
    def reject(user, wind_up_id):
        wind_up = WelfareWindUp.objects.select_for_update().get(
            id=wind_up_id, status=WelfareWindUp.Status.PENDING)
        require(user, "community.finance.manage", wind_up.fund.community,
                "Only community admins can reject winding up the welfare fund.")
        if wind_up.requested_by_id == user.id:
            raise PermissionDenied("You cannot reject your own proposal; cancel it instead.")
        wind_up.status = WelfareWindUp.Status.REJECTED
        wind_up.decided_by = user
        wind_up.decided_at = timezone.now()
        wind_up.save(update_fields=['status', 'decided_by', 'decided_at'])
        return wind_up

    @staticmethod
    @transaction.atomic
    def cancel(user, wind_up_id):
        wind_up = WelfareWindUp.objects.select_for_update().get(
            id=wind_up_id, status=WelfareWindUp.Status.PENDING)
        if wind_up.requested_by_id != user.id:
            raise PermissionDenied("Only the proposer can cancel this wind-up.")
        wind_up.status = WelfareWindUp.Status.CANCELLED
        wind_up.save(update_fields=['status'])
        return wind_up

    @staticmethod
    def _execute(wind_up, *, decided_by) -> None:
        fund = WelfareFund.objects.select_for_update().get(id=wind_up.fund_id)
        WelfareWindUpService._check(fund)
        leftover = fund_balance('welfare', fund.id)
        members = WelfareWindUpService.paid_up_members(fund)
        shares = (_apportion_amount(leftover, [(u.id, Decimal('1')) for u in members])
                  if leftover > 0 else {})

        dispatch = []
        for member in members:
            share = shares.get(member.id, Decimal('0'))
            if share <= 0:
                continue
            payout = WelfareWindUpPayout.objects.create(
                wind_up=wind_up, member=member, amount=share)
            idem_key = f"welfare-windup-{payout.id}"
            # A wind-up share leaves the fund exactly as a claim does, so it
            # posts the claim recipe and stays inside the payout controls.
            ft, _ = create_fin_transaction(
                idempotency_key=idem_key,
                op_type=FinancialTransaction.OpType.WELFARE_CLAIM,
                amount=share,
                initiated_by=member,
                recipient_phone=member.phone_number,
                welfare_fund=fund,
                context_type='welfare_wind_up',
                context_id=payout.id,
            )
            post_journal(
                idempotency_key=f"je-{idem_key}",
                op_type=_pm.Op.WELFARE_CLAIM,
                lines=_pm.welfare_claim_lines(fund_id=fund.id, amount=Money(str(share))),
                narration=f"Welfare wind-up: per-head share — {fund}"[:120],
                financial_transaction=ft,
                created_by=decided_by,
            )
            dispatch.append(ft.id)
            _notify(
                user=member,
                notification_type='welfare_disbursed',
                title="Welfare fund wound up",
                message=(f"Your share of KES {share:,.2f} from the welfare fund "
                         "is being sent to your M-Pesa."),
            )

        def _dispatch():
            from apps.payments.payouts import execute_payout
            from apps.core.dispatch import safe_enqueue
            for ft_id in dispatch:
                safe_enqueue(execute_payout, ft_id, critical=True)

        transaction.on_commit(_dispatch)

        now = timezone.now()
        fund.closed_at = now
        fund.save(update_fields=['closed_at'])
        wind_up.status = WelfareWindUp.Status.EXECUTED
        wind_up.decided_by = decided_by
        wind_up.decided_at = now
        wind_up.amount = leftover
        wind_up.save(update_fields=['status', 'decided_by', 'decided_at', 'amount'])
        AuditService.log(
            "welfare.wound_up", actor=decided_by, target=wind_up,
            tenant=getattr(fund.community, "tenant_id", None),
            metadata={"amount": str(leftover), "members_paid": len(dispatch),
                      "requested_by": wind_up.requested_by_id},
        )
