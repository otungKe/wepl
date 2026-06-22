"""Phase 5 multi-currency tests — per-currency balancing, FX rates, conversion,
and per-currency trial balance."""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.ledger import fx, reporting
from apps.ledger.exceptions import UnbalancedJournalError
from apps.ledger.models import Account, ExchangeRate, JournalLine
from apps.ledger.money import Money
from apps.ledger.posting import Line, post_journal


def _acct(code, ccy, type_=Account.Type.ASSET):
    return Account.objects.create(code=code, name=code, type=type_, currency=ccy)


class PerCurrencyBalancingTests(TestCase):
    def setUp(self):
        self.usd1 = _acct('USD-A', 'USD')
        self.usd2 = _acct('USD-B', 'USD', Account.Type.LIABILITY)
        self.kes1 = _acct('KES-A', 'KES')

    def test_single_currency_journal_balances(self):
        je = post_journal(
            idempotency_key='fx-ok', op_type='CONTRIBUTION',
            lines=[
                Line(account=self.usd1, direction=JournalLine.Direction.DEBIT, amount=Decimal('100')),
                Line(account=self.usd2, direction=JournalLine.Direction.CREDIT, amount=Decimal('100')),
            ],
        )
        self.assertIsNotNone(je.id)

    def test_journal_unbalanced_within_a_currency_rejected(self):
        # Debits in USD, credit in KES — each currency is one-sided → not balanced.
        with self.assertRaises(UnbalancedJournalError):
            post_journal(
                idempotency_key='fx-bad', op_type='CONTRIBUTION',
                lines=[
                    Line(account=self.usd1, direction=JournalLine.Direction.DEBIT, amount=Decimal('100')),
                    Line(account=self.kes1, direction=JournalLine.Direction.CREDIT, amount=Decimal('100')),
                ],
            )


class ExchangeRateTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        ExchangeRate.objects.create(base_currency='USD', quote_currency='KES', rate=Decimal('130'),
                                    effective_at=self.now - timedelta(days=1))

    def test_same_currency_is_one(self):
        self.assertEqual(fx.get_rate('KES', 'KES'), Decimal('1'))

    def test_direct_rate(self):
        self.assertEqual(fx.get_rate('USD', 'KES'), Decimal('130'))

    def test_inverse_rate(self):
        self.assertEqual(fx.get_rate('KES', 'USD'), Decimal('1') / Decimal('130'))

    def test_effective_dating(self):
        ExchangeRate.objects.create(base_currency='USD', quote_currency='KES', rate=Decimal('140'),
                                    effective_at=self.now)
        # latest effective rate wins
        self.assertEqual(fx.get_rate('USD', 'KES'), Decimal('140'))
        # but a past lookup gets the older rate
        self.assertEqual(fx.get_rate('USD', 'KES', at=self.now - timedelta(hours=1)), Decimal('130'))

    def test_missing_rate_raises(self):
        with self.assertRaises(fx.RateNotFound):
            fx.get_rate('USD', 'EUR')

    def test_convert(self):
        out = fx.convert(Money('10', 'USD'), 'KES')
        self.assertEqual(out, Money('1300', 'KES'))

    def test_convert_no_implicit_same_currency(self):
        self.assertEqual(fx.convert(Money('10', 'KES'), 'KES'), Money('10', 'KES'))


class CrossCurrencyJournalTests(TestCase):
    def setUp(self):
        self.usd_src = _acct('USD-SRC', 'USD')
        self.usd_clr = _acct('USD-CLR', 'USD', Account.Type.LIABILITY)
        self.kes_dst = _acct('KES-DST', 'KES')
        self.kes_clr = _acct('KES-CLR', 'KES', Account.Type.LIABILITY)
        ExchangeRate.objects.create(base_currency='USD', quote_currency='KES', rate=Decimal('130'),
                                    effective_at=timezone.now() - timedelta(days=1))

    def test_cross_currency_settlement_posts_balanced_per_currency(self):
        lines = fx.conversion_lines(
            source_account=self.usd_src, source_clearing=self.usd_clr,
            dest_account=self.kes_dst, dest_clearing=self.kes_clr,
            source_money=Money('100', 'USD'), to_currency='KES',
            note='FX settlement',
        )
        je = post_journal(idempotency_key='fx-conv', op_type='DISBURSEMENT', lines=lines)
        self.assertIsNotNone(je.id)
        # Per-currency trial balance holds for both currencies.
        tbc = reporting.trial_balance_by_currency()
        self.assertTrue(tbc['balanced'])
        self.assertTrue(tbc['currencies']['USD']['balanced'])
        self.assertTrue(tbc['currencies']['KES']['balanced'])
        self.assertEqual(tbc['currencies']['KES']['total_debit'], Decimal('13000'))  # 100 × 130
