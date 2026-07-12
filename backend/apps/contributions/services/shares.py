"""Shares purchase — the domain money-operation for buying into a SharesFund.

Relocated out of ``apps/mpesa/views._process_shares_purchase`` (Move 2): a shares
purchase is a *contributions* money operation (ShareHolding + a double-entry
posting), not rail plumbing. It is provider-agnostic — it takes a user, a fund, an
amount and an idempotency seed, and knows nothing about M-Pesa. The STK collection
callback now routes here through ``contributions.settlement.on_collection_settled``.
"""
from decimal import Decimal as D

from django.db import transaction
from django.db.models import F

from ..models import ShareHolding, SharesFund


class SharesService:

    @staticmethod
    @transaction.atomic
    def purchase(user, shares_fund_id, amount, *, mpesa_receipt=None,
                 idempotency_key=None):
        """Credit a member's share holding for a settled purchase and post the
        double-entry (cash into the float, member shares liability up). Idempotent
        on the receipt / idempotency seed."""
        from apps.ledger.models import FinancialTransaction
        from apps.ledger.money import Money
        from apps.ledger.posting import post_journal
        from apps.ledger import posting_map as pm
        from apps.ledger.writer import create_fin_transaction

        fund = SharesFund.objects.select_for_update().get(id=shares_fund_id)
        amount = D(str(amount))
        new_shares = (amount / fund.share_price).quantize(D('0.0001'))

        # F() updates — atomic, no read-modify-write race.
        ShareHolding.objects.update_or_create(
            shares_fund=fund, user=user,
            defaults={'shares_count': D('0'), 'total_contributed': D('0')},
        )
        ShareHolding.objects.filter(shares_fund=fund, user=user).update(
            shares_count=F('shares_count') + new_shares,
            total_contributed=F('total_contributed') + amount,
        )

        seed = mpesa_receipt or idempotency_key
        idem_key = f"shares-{fund.id}-{user.id}-{seed}"
        ft, _ = create_fin_transaction(
            idempotency_key=idem_key,
            op_type=FinancialTransaction.OpType.SHARES_PURCHASE,
            amount=amount,
            initiated_by=user,
            shares_fund=fund,
            initial_state=FinancialTransaction.State.SUCCESS,
        )
        post_journal(
            idempotency_key=f"je-{idem_key}",
            op_type=pm.Op.SHARES_PURCHASE,
            lines=pm.contribution_lines(
                member=user, fund_type='shares', fund_id=fund.id,
                gross=Money(str(amount)),
            ),
            narration=f"Shares purchase by {getattr(user, 'phone_number', user.pk)}",
            financial_transaction=ft,
            created_by=user,
        )
        return ft
