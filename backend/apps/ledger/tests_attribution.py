"""Tests for attribution, the economic-interest seam, and custody (ADR-0027).

These cover the "four commitments" increment: payment ≠ ownership (an attributed
contribution credits the *beneficiaries*, not the payer), economic interest as a
derivation, and a custody/legal-title anchor on every pool. The global trial
balance must stay zero throughout.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ledger import coa, posting_map as pm
from apps.ledger.balances import account_balance, economic_interest, trial_balance
from apps.ledger.models import CustodyArrangement
from apps.ledger.money import Money
from apps.ledger.posting import post_journal

User = get_user_model()


class AttributionTests(TestCase):

    def setUp(self):
        coa.seed_chart_of_accounts()
        self.alice = User.objects.create(phone_number="+254700000920")
        self.bob = User.objects.create(phone_number="+254700000921")
        self.float = coa.mpesa_float_account()

    def _acct(self, user):
        return coa.member_fund_account(user=user, fund_type="contribution", fund_id=7)

    def test_payment_is_not_ownership_split_across_beneficiaries(self):
        """Alice pays KES 10,000: 6,000 attributed to herself, 4,000 to Bob."""
        lines = pm.attributed_contribution_lines(
            fund_type="contribution", fund_id=7,
            allocations=[
                pm.Allocation(member=self.alice, amount=Money("6000")),
                pm.Allocation(member=self.bob, amount=Money("4000")),
            ],
        )
        post_journal(idempotency_key="attr-1", op_type=pm.Op.CONTRIBUTION, lines=lines)

        # Cash arrived in float for the full gross; ownership landed on the
        # *attributed* members, not the payer alone.
        self.assertEqual(account_balance(self.float), Decimal("10000.0000"))
        self.assertEqual(account_balance(self._acct(self.alice)), Decimal("6000.0000"))
        self.assertEqual(account_balance(self._acct(self.bob)), Decimal("4000.0000"))
        self.assertTrue(trial_balance()["balanced"])

    def test_attributed_contribution_with_fee(self):
        """Fee is drawn from the gross; beneficiaries keep their net allocations."""
        lines = pm.attributed_contribution_lines(
            fund_type="contribution", fund_id=7,
            allocations=[
                pm.Allocation(member=self.alice, amount=Money("5000")),
                pm.Allocation(member=self.bob, amount=Money("4000")),
            ],
            fee=Money("100"),
        )
        post_journal(idempotency_key="attr-fee", op_type=pm.Op.CONTRIBUTION, lines=lines)

        self.assertEqual(account_balance(self.float), Decimal("9100.0000"))       # 5000+4000+100
        self.assertEqual(account_balance(self._acct(self.alice)), Decimal("5000.0000"))
        self.assertEqual(account_balance(self._acct(self.bob)), Decimal("4000.0000"))
        self.assertEqual(account_balance(coa.fee_revenue_account()), Decimal("100.0000"))
        self.assertTrue(trial_balance()["balanced"])

    def test_identity_attribution_matches_simple_contribution(self):
        """contribution_lines is the single-beneficiary case and must be identical."""
        simple = pm.contribution_lines(
            member=self.alice, fund_type="contribution", fund_id=7,
            gross=Money("1000"), fee=Money("50"))
        attributed = pm.attributed_contribution_lines(
            fund_type="contribution", fund_id=7,
            allocations=[pm.Allocation(member=self.alice, amount=Money("950"))],
            fee=Money("50"))
        # Same accounts, directions and amounts, in the same order.
        self.assertEqual(
            [(l.account.pk, l.direction, l.amount) for l in simple],
            [(l.account.pk, l.direction, l.amount) for l in attributed],
        )

    def test_empty_allocations_rejected(self):
        with self.assertRaises(ValueError):
            pm.attributed_contribution_lines(
                fund_type="contribution", fund_id=7, allocations=[])

    def test_economic_interest_is_the_derived_liability(self):
        """For a debt fund, economic interest == the member's redeemable balance."""
        post_journal(
            idempotency_key="attr-ei", op_type=pm.Op.CONTRIBUTION,
            lines=pm.attributed_contribution_lines(
                fund_type="contribution", fund_id=7,
                allocations=[
                    pm.Allocation(member=self.alice, amount=Money("6000")),
                    pm.Allocation(member=self.bob, amount=Money("4000")),
                ]))
        self.assertEqual(economic_interest(self.alice, "contribution", 7), Decimal("6000.0000"))
        self.assertEqual(economic_interest(self.bob, "contribution", 7), Decimal("4000.0000"))
        # A party with no position has zero derived interest (no account minted).
        carol = User.objects.create(phone_number="+254700000922")
        self.assertEqual(economic_interest(carol, "contribution", 7), Decimal("0"))


class CustodyAnchorTests(TestCase):

    def setUp(self):
        coa.seed_chart_of_accounts()
        self.alice = User.objects.create(phone_number="+254700000930")

    def test_pool_birth_creates_a_trust_custody_anchor(self):
        """Resolving a pool anchors its custody: platform holds it in trust."""
        coa.member_fund_account(user=self.alice, fund_type="welfare", fund_id=3)
        arrangement = CustodyArrangement.objects.get(fund_type="welfare", fund_id=3)
        self.assertEqual(arrangement.legal_basis, CustodyArrangement.LegalBasis.TRUST)
        self.assertIn("trust", arrangement.trustee_label.lower())

    def test_ensure_custody_is_idempotent(self):
        coa.ensure_custody(fund_type="shares", fund_id=9)
        coa.ensure_custody(fund_type="shares", fund_id=9)
        self.assertEqual(
            CustodyArrangement.objects.filter(fund_type="shares", fund_id=9).count(), 1)
