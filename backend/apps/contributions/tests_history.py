"""Parity tests for the ledger-derived member history (retires the CT shadow log).

member_summary / member_contribution_credits read straight from journal lines on
the member's sub-ledgers; member_history_qs derives the transaction list from the
FinancialTransactions whose journal touches an account the member owns. These must
match what actually moved on the ledger — including attributed (gifted)
contributions surfacing on the *beneficiary's* history.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.contributions.history import (
    member_contribution_credits, member_history_qs, member_summary, transaction_type_for,
)
from apps.ledger import coa, posting_map as pm
from apps.ledger.models import FinancialTransaction
from apps.ledger.money import Money
from apps.ledger.posting import post_journal

User = get_user_model()


class MemberSummaryTests(TestCase):
    def setUp(self):
        coa.seed_chart_of_accounts()
        self.alice = User.objects.create(phone_number="+254700000940")
        self.bob = User.objects.create(phone_number="+254700000941")

    def test_summary_from_sub_ledger_credits_and_debits(self):
        # Alice contributes 1000; then 300 is paid back out to her.
        post_journal(idempotency_key="h-c1", op_type=pm.Op.CONTRIBUTION,
                     lines=pm.contribution_lines(member=self.alice, fund_type="contribution",
                                                 fund_id=5, gross=Money("1000")))
        post_journal(idempotency_key="h-d1", op_type=pm.Op.DISBURSEMENT,
                     lines=pm.disbursement_lines(member=self.alice, fund_type="contribution",
                                                 fund_id=5, amount=Money("300")))
        s = member_summary(self.alice)
        self.assertEqual(s["total_contributed"], Decimal("1000.0000"))
        self.assertEqual(s["total_received"], Decimal("300.0000"))

    def test_attributed_contribution_credits_the_beneficiary_not_the_payer(self):
        # Alice pays; ownership split 600 → Alice, 400 → Bob.
        post_journal(idempotency_key="h-attr", op_type=pm.Op.CONTRIBUTION,
                     lines=pm.attributed_contribution_lines(
                         fund_type="contribution", fund_id=5,
                         allocations=[pm.Allocation(member=self.alice, amount=Money("600")),
                                      pm.Allocation(member=self.bob, amount=Money("400"))]))
        self.assertEqual(member_summary(self.alice)["total_contributed"], Decimal("600.0000"))
        self.assertEqual(member_summary(self.bob)["total_contributed"], Decimal("400.0000"))
        self.assertEqual(member_contribution_credits(self.bob).count(), 1)


class MemberHistoryQsTests(TestCase):
    def setUp(self):
        coa.seed_chart_of_accounts()
        self.alice = User.objects.create(phone_number="+254700000942")
        self.contribution = self._make_contribution()

    def _make_contribution(self):
        from apps.communities.services import CommunityService
        from apps.contributions.models import Contribution
        community = CommunityService.create_community(self.alice, {"name": "Chama"})
        return Contribution.objects.create(
            community=community, title="Holiday", created_by=self.alice)

    def test_history_lists_the_members_settled_movements(self):
        ft = FinancialTransaction.objects.create(
            op_type=FinancialTransaction.OpType.CONTRIBUTION,
            amount=Decimal("1000"), initiated_by=self.alice,
            contribution=self.contribution,
            state=FinancialTransaction.State.SUCCESS, idempotency_key="ft-h1")
        post_journal(idempotency_key="je-h1", op_type=pm.Op.CONTRIBUTION,
                     lines=pm.contribution_lines(member=self.alice, fund_type="contribution",
                                                 fund_id=self.contribution.id, gross=Money("1000")),
                     financial_transaction=ft)
        rows = list(member_history_qs(self.alice))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].id, ft.id)
        self.assertEqual(transaction_type_for(rows[0].op_type), "CONTRIBUTION")
        # Scoped fetch works too.
        self.assertEqual(member_history_qs(self.alice, contribution=self.contribution).count(), 1)

    def test_history_excludes_members_with_no_movement(self):
        stranger = User.objects.create(phone_number="+254700000943")
        self.assertEqual(member_history_qs(stranger).count(), 0)
