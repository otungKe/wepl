"""Regression cover for ``execute_due_standing_orders`` — the scheduled payout
task that had never once run.

The task evaluated a ``select_for_update(skip_locked=True)`` queryset with no
surrounding transaction, so Django raised ``TransactionManagementError`` on
every invocation and the beat entry (08:00 / 12:00 / 18:00 EAT) silently
executed nothing. These are the first tests the task has ever had, and they use
``TransactionTestCase``: a plain ``TestCase`` wraps each test in an atomic block,
which would have hidden the original failure entirely.
"""
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from django.utils import timezone

from apps.communities.services import CommunityService
from apps.contributions.models import StandingOrder
from apps.contributions.services import ContributionService
from apps.contributions.tasks import execute_due_standing_orders
from apps.ledger import coa, posting_map as pm
from apps.ledger.balances import fund_balance, trial_balance
from apps.ledger.money import Money
from apps.ledger.posting import post_journal

User = get_user_model()


class ExecuteDueStandingOrdersTests(TransactionTestCase):
    def setUp(self):
        coa.seed_chart_of_accounts()
        self.admin = User.objects.create(phone_number="+254700000980")
        CommunityService.create_community(self.admin, {"name": "Rent Pool"})
        self.contribution = ContributionService.create_contribution(
            self.admin, {"title": "Monthly rent"})
        self.cid = self.contribution.id
        post_journal(
            idempotency_key="so-task-funding",
            op_type=pm.Op.CONTRIBUTION,
            lines=pm.contribution_lines(
                member=self.admin, fund_type="contribution",
                fund_id=self.cid, gross=Money("10000"),
            ),
        )

    def _order(self, *, amount="1000", due=True, phone="+254711000111"):
        now = timezone.now()
        return StandingOrder.objects.create(
            contribution=self.contribution,
            created_by=self.admin,
            amount=Decimal(amount),
            frequency="monthly",
            payee_type="fixed",
            fixed_payee_phone=phone,
            next_run_at=now - timedelta(minutes=1) if due else now + timedelta(days=1),
        )

    def test_a_due_order_is_executed(self):
        """Pre-change this raised TransactionManagementError before touching a
        single order, which is why no standing order has ever been paid."""
        order = self._order(amount="1000")
        with mock.patch("apps.core.dispatch.safe_enqueue") as enqueue:
            self.assertEqual(execute_due_standing_orders(), 1)

        order.refresh_from_db()
        self.assertIsNotNone(order.last_executed_at)
        self.assertGreater(order.next_run_at, timezone.now())
        # Money actually left the pool, and the books still balance.
        self.assertEqual(fund_balance("contribution", self.cid), Decimal("9000"))
        self.assertTrue(trial_balance()["balanced"])
        # The B2C leg is dispatched after the order's own transaction commits.
        self.assertEqual(enqueue.call_count, 1)

    def test_an_order_that_is_not_due_is_left_alone(self):
        order = self._order(due=False)
        with mock.patch("apps.core.dispatch.safe_enqueue"):
            self.assertEqual(execute_due_standing_orders(), 0)
        order.refresh_from_db()
        self.assertIsNone(order.last_executed_at)
        self.assertEqual(fund_balance("contribution", self.cid), Decimal("10000"))

    def test_a_second_pass_does_not_pay_out_again(self):
        """The due predicate is re-checked under the row lock. Without that a
        second pass would re-run the order against a fresh next_run_at — and the
        idempotency key is anchored to next_run_at, so it would mint a new key
        and pay out twice rather than dedupe."""
        self._order(amount="1000")
        with mock.patch("apps.core.dispatch.safe_enqueue"):
            self.assertEqual(execute_due_standing_orders(), 1)
            self.assertEqual(execute_due_standing_orders(), 0)
        self.assertEqual(fund_balance("contribution", self.cid), Decimal("9000"))

    def test_an_inactive_order_is_skipped(self):
        order = self._order()
        StandingOrder.objects.filter(pk=order.pk).update(is_active=False)
        with mock.patch("apps.core.dispatch.safe_enqueue"):
            self.assertEqual(execute_due_standing_orders(), 0)
        self.assertEqual(fund_balance("contribution", self.cid), Decimal("10000"))

    def test_one_failing_order_does_not_stop_the_others(self):
        """A ValidationError (here: more than the pool holds) is expected traffic.
        It must not abort the batch, and it must not roll back the order that
        already succeeded — which is why each order gets its own transaction."""
        self._order(amount="999999", phone="+254711000222")   # insufficient funds
        self._order(amount="1000", phone="+254711000333")
        with mock.patch("apps.core.dispatch.safe_enqueue") as enqueue:
            self.assertEqual(execute_due_standing_orders(), 1)
        self.assertEqual(enqueue.call_count, 1)
        self.assertEqual(fund_balance("contribution", self.cid), Decimal("9000"))
        self.assertTrue(trial_balance()["balanced"])

    def test_no_due_orders_is_a_quiet_zero(self):
        self.assertEqual(execute_due_standing_orders(), 0)


class StandingOrderOwnershipTests(TransactionTestCase):
    """ADR-0027 §0.1: a standing order spends the group's money. It never
    charges whoever runs it. A fixed payee is a group expense split across
    shares; a rotating payee draws their turn from their own share."""

    def setUp(self):
        from apps.contributions.models import ContributionParticipant
        coa.seed_chart_of_accounts()
        self.admin = User.objects.create(phone_number="+254700000990")
        self.bob = User.objects.create(phone_number="+254700000991")
        CommunityService.create_community(self.admin, {"name": "Split Rent"})
        self.contribution = ContributionService.create_contribution(
            self.admin, {"title": "Rent"})
        ContributionParticipant.objects.create(
            contribution=self.contribution, user=self.bob, is_active=True)
        self.cid = self.contribution.id
        for member, amount in ((self.admin, "6000"), (self.bob, "4000")):
            post_journal(
                idempotency_key=f"so-own-{member.pk}", op_type=pm.Op.CONTRIBUTION,
                lines=pm.contribution_lines(member=member, fund_type="contribution",
                                            fund_id=self.cid, gross=Money(amount)))

    def _share(self, member):
        from apps.ledger.balances import member_fund_balance
        return member_fund_balance(member, "contribution", self.cid)

    def test_fixed_payee_is_split_across_shares(self):
        from apps.contributions.services import StandingOrderService
        order = StandingOrder.objects.create(
            contribution=self.contribution, created_by=self.admin, amount=Decimal("1000"),
            frequency="monthly", payee_type="fixed", fixed_payee_phone="+254711000222",
            next_run_at=timezone.now())
        with mock.patch("apps.core.dispatch.safe_enqueue"):
            StandingOrderService.execute_standing_order(order.id, self.admin)
        self.assertEqual(self._share(self.admin), Decimal("5400"))   # 6000 − 600
        self.assertEqual(self._share(self.bob), Decimal("3600"))     # 4000 − 400
        self.assertTrue(trial_balance()["balanced"])

    def test_rotating_payee_draws_their_own_share(self):
        from apps.contributions.models import StandingOrderSlot
        from apps.contributions.services import StandingOrderService
        order = StandingOrder.objects.create(
            contribution=self.contribution, created_by=self.admin, amount=Decimal("1000"),
            frequency="monthly", payee_type="rotating", next_run_at=timezone.now())
        StandingOrderSlot.objects.create(order=order, phone_number=self.bob.phone_number,
                                         slot_order=1)
        with mock.patch("apps.core.dispatch.safe_enqueue"):
            StandingOrderService.execute_standing_order(order.id, self.admin)
        self.assertEqual(self._share(self.admin), Decimal("6000"))
        self.assertEqual(self._share(self.bob), Decimal("3000"))
        self.assertTrue(trial_balance()["balanced"])
