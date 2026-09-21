"""Shares purchase — the domain money-operation for buying into a SharesFund.

Relocated out of ``apps/mpesa/views._process_shares_purchase`` (Move 2): a shares
purchase is a *contributions* money operation (a double-entry posting plus fund
membership), not rail plumbing. It is provider-agnostic — it takes a user, a fund, an
amount and an idempotency seed, and knows nothing about M-Pesa. The STK collection
callback now routes here through ``contributions.settlement.on_collection_settled``.
"""
from decimal import Decimal as D

from django.db import transaction

from ..models import ShareHolding, SharesFund


class SharesService:

    @staticmethod
    @transaction.atomic
    def purchase(user, shares_fund_id, amount, *, mpesa_receipt=None,
                 idempotency_key=None):
        """Post the double-entry for a settled purchase (cash into the float,
        member shares liability up) and make sure the member is on the fund.
        Idempotent on the receipt / idempotency seed — the holding's amounts are
        read back off this posting, never stored."""
        from apps.ledger.models import FinancialTransaction, JournalEntry
        from apps.ledger.money import Money
        from apps.ledger.posting import post_journal
        from apps.ledger import posting_map as pm
        from apps.ledger.writer import create_fin_transaction

        fund = SharesFund.objects.select_for_update().get(id=shares_fund_id)
        amount = D(str(amount))

        seed = mpesa_receipt or idempotency_key
        idem_key = f"shares-{fund.id}-{user.id}-{seed}"

        # ── Idempotency: if this journal was already posted, return its FT ─────
        # post_journal dedupes on its own key, but the ShareHolding counters below
        # are a SEPARATE write that key does not cover — a replayed settlement
        # (at-least-once delivery) would credit the holding twice. Guard on the
        # journal first, the same check ContributionService.contribute makes.
        # The fund row is locked above, so this check and the update below cannot
        # interleave with a concurrent purchase into the same fund.
        if JournalEntry.objects.filter(idempotency_key=f"je-{idem_key}").exists():
            return FinancialTransaction.objects.filter(idempotency_key=idem_key).first()

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

        # ── Membership row ────────────────────────────────────────────────────
        # No counters to move: ShareHolding.shares_count / .total_contributed are
        # derived from the sub-ledger the posting above just wrote. All this
        # ensures is that the member appears among the fund's holders.
        ShareHolding.objects.get_or_create(shares_fund=fund, user=user)
        return ft
