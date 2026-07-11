"""Controls tests — limits engine + posting-chokepoint enforcement."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.controls.engine import classify_direction, enforce_controls, evaluate
from apps.controls.models import ControlDecision, LimitRule
from apps.core.exceptions import ControlHeld, LimitExceeded
from apps.ledger.coa import seed_chart_of_accounts
from apps.ledger.models import Account, FinancialTransaction, JournalEntry, JournalLine
from apps.ledger.posting import Line, post_journal

User = get_user_model()


def _ft(user, op_type, amount):
    return FinancialTransaction.objects.create(
        op_type=op_type, amount=Decimal(amount), initiated_by=user,
        idempotency_key=f"ft-{op_type}-{amount}-{user.id}-{FinancialTransaction.objects.count()}",
    )


class DirectionClassificationTests(TestCase):
    def test_payin_and_payout_classification(self):
        self.assertEqual(classify_direction('DISBURSEMENT'), LimitRule.Direction.PAYOUT)
        self.assertEqual(classify_direction('CONTRIBUTION'), LimitRule.Direction.PAYIN)
        self.assertIsNone(classify_direction('SOMETHING_ELSE'))


class LimitEngineTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(phone_number='254700000001')

    def test_per_transaction_cap_denies(self):
        LimitRule.objects.create(name='txn cap', direction='PAYOUT', period='TXN',
                                 max_amount=Decimal('1000'), action='DENY')
        d = evaluate(subject_user_id=self.user.id, op_type='DISBURSEMENT',
                     direction='PAYOUT', amount=Decimal('1500'))
        self.assertEqual(d.decision, ControlDecision.Outcome.DENY)

    def test_within_cap_allows(self):
        LimitRule.objects.create(name='txn cap', direction='PAYOUT', period='TXN',
                                 max_amount=Decimal('2000'), action='DENY')
        d = evaluate(subject_user_id=self.user.id, op_type='DISBURSEMENT',
                     direction='PAYOUT', amount=Decimal('1500'))
        self.assertEqual(d.decision, ControlDecision.Outcome.ALLOW)

    def test_daily_window_accumulates(self):
        LimitRule.objects.create(name='daily', direction='PAYOUT', period='DAY',
                                 max_amount=Decimal('1000'), action='DENY')
        _ft(self.user, 'DISBURSEMENT', '800')  # prior in-window movement
        d = evaluate(subject_user_id=self.user.id, op_type='DISBURSEMENT',
                     direction='PAYOUT', amount=Decimal('300'))
        self.assertEqual(d.decision, ControlDecision.Outcome.DENY)  # 800 + 300 > 1000

    def test_velocity_count_holds(self):
        LimitRule.objects.create(name='velocity', direction='PAYOUT', period='HOUR',
                                 max_count=2, action='HOLD')
        _ft(self.user, 'DISBURSEMENT', '10')
        _ft(self.user, 'DISBURSEMENT', '10')
        d = evaluate(subject_user_id=self.user.id, op_type='DISBURSEMENT',
                     direction='PAYOUT', amount=Decimal('10'))
        self.assertEqual(d.decision, ControlDecision.Outcome.HOLD)  # 3rd in the hour

    def test_deny_takes_precedence_over_hold(self):
        LimitRule.objects.create(name='hold', direction='PAYOUT', period='TXN', max_amount=Decimal('100'), action='HOLD', priority=10)
        LimitRule.objects.create(name='deny', direction='PAYOUT', period='TXN', max_amount=Decimal('100'), action='DENY', priority=20)
        d = evaluate(subject_user_id=self.user.id, op_type='DISBURSEMENT', direction='PAYOUT', amount=Decimal('500'))
        self.assertEqual(d.decision, ControlDecision.Outcome.DENY)


class ChokepointEnforcementTests(TestCase):
    def setUp(self):
        seed_chart_of_accounts()
        self.user = User.objects.create_user(phone_number='254700000002')
        self.a = Account.objects.first()
        self.b = Account.objects.exclude(pk=self.a.pk).first()

    def _post(self, ft):
        return post_journal(
            idempotency_key=f"je-{ft.idempotency_key}",
            op_type=ft.op_type,
            financial_transaction=ft,
            lines=[
                Line(account=self.a, direction=JournalLine.Direction.DEBIT, amount=ft.amount),
                Line(account=self.b, direction=JournalLine.Direction.CREDIT, amount=ft.amount),
            ],
        )

    def test_post_journal_rejects_over_limit_before_writing(self):
        LimitRule.objects.create(name='cap', direction='PAYOUT', period='TXN', max_amount=Decimal('1000'), action='DENY')
        ft = _ft(self.user, 'DISBURSEMENT', '5000')
        with self.assertRaises(LimitExceeded):
            self._post(ft)
        # No journal was written for this FT.
        self.assertFalse(JournalEntry.objects.filter(financial_transaction=ft).exists())

    def test_post_journal_allows_within_limit(self):
        LimitRule.objects.create(name='cap', direction='PAYOUT', period='TXN', max_amount=Decimal('10000'), action='DENY')
        ft = _ft(self.user, 'DISBURSEMENT', '5000')
        je = self._post(ft)
        self.assertTrue(JournalEntry.objects.filter(pk=je.pk).exists())

    def test_hold_blocks_posting(self):
        LimitRule.objects.create(name='hold', direction='PAYOUT', period='TXN', max_amount=Decimal('1000'), action='HOLD')
        ft = _ft(self.user, 'DISBURSEMENT', '5000')
        with self.assertRaises(ControlHeld):
            self._post(ft)

    def test_no_rules_allows(self):
        ft = _ft(self.user, 'DISBURSEMENT', '999999')
        je = self._post(ft)
        self.assertTrue(JournalEntry.objects.filter(pk=je.pk).exists())


class HeldMovementReviewTests(TestCase):
    """blocked movements are durably recorded and reviewable."""

    def setUp(self):
        self.user = User.objects.create_user(phone_number='254700000003')

    def test_held_exception_carries_context_and_records(self):
        from apps.controls.models import HeldMovement
        from apps.controls.review import record_blocked_movement
        LimitRule.objects.create(name='hold', direction='PAYOUT', period='TXN', max_amount=Decimal('100'), action='HOLD')
        ft = _ft(self.user, 'DISBURSEMENT', '500')
        with self.assertRaises(ControlHeld) as cm:
            enforce_controls(financial_transaction=ft, amount=Decimal('500'))
        self.assertEqual(cm.exception.context['decision'], 'HOLD')
        item = record_blocked_movement(cm.exception)
        self.assertEqual(item.status, HeldMovement.Status.OPEN)
        self.assertEqual(item.decision, 'HOLD')
        self.assertEqual(item.amount, Decimal('500'))
        self.assertEqual(item.subject_user_id, self.user.id)

    def test_denied_movement_recorded(self):
        from apps.controls.models import HeldMovement
        from apps.controls.review import record_blocked_movement
        LimitRule.objects.create(name='deny', direction='PAYOUT', period='TXN', max_amount=Decimal('100'), action='DENY')
        ft = _ft(self.user, 'DISBURSEMENT', '500')
        with self.assertRaises(LimitExceeded) as cm:
            enforce_controls(financial_transaction=ft, amount=Decimal('500'))
        item = record_blocked_movement(cm.exception)
        self.assertEqual(item.decision, HeldMovement.Decision.DENY)

    def test_release_action_marks_released(self):
        from apps.controls.admin import release_movements
        from apps.controls.models import HeldMovement
        item = HeldMovement.objects.create(decision='HOLD', op_type='DISBURSEMENT', direction='PAYOUT', amount=Decimal('5'))

        class _MA:
            def message_user(self, *a, **k): pass
        class _Req:
            user = self.user
        release_movements(_MA(), _Req(), HeldMovement.objects.filter(pk=item.pk))
        item.refresh_from_db()
        self.assertEqual(item.status, HeldMovement.Status.RELEASED)
        self.assertEqual(item.reviewed_by_id, self.user.id)


class SeedControlsCommandTests(TestCase):
    def test_seed_creates_rules(self):
        from django.core.management import call_command
        call_command('seed_controls')
        self.assertTrue(LimitRule.objects.filter(name='Daily payout cap (per user)').exists())
