"""Tests for the Money value object (ADR-0003)."""
from decimal import Decimal

from django.test import SimpleTestCase

from apps.ledger.money import (
    Money, MoneyError, CurrencyMismatch, quantize, PLACES, DEFAULT_CURRENCY,
)


class QuantizeTests(SimpleTestCase):
    def test_default_precision_is_four_places(self):
        self.assertEqual(quantize("1.23456789"), Decimal("1.2346"))
        self.assertEqual(PLACES, 4)

    def test_bankers_rounding_half_to_even(self):
        # ROUND_HALF_EVEN: .5 rounds to the nearest even digit.
        self.assertEqual(quantize(Decimal("2.50"), places=0), Decimal("2"))
        self.assertEqual(quantize(Decimal("3.50"), places=0), Decimal("4"))
        self.assertEqual(quantize(Decimal("0.00005"), places=4), Decimal("0.0000"))
        self.assertEqual(quantize(Decimal("0.00015"), places=4), Decimal("0.0002"))

    def test_float_coerced_via_str(self):
        # 0.1 + 0.2 as floats is 0.30000000000000004; Money must not inherit that.
        self.assertEqual(quantize(0.1) + quantize(0.2), Decimal("0.3000"))

    def test_invalid_amount_raises(self):
        with self.assertRaises(MoneyError):
            quantize("not-a-number")


class MoneyConstructionTests(SimpleTestCase):
    def test_amount_is_normalised_to_storage_precision(self):
        self.assertEqual(Money("10").amount, Decimal("10.0000"))
        self.assertEqual(Money("1.23456").amount, Decimal("1.2346"))

    def test_default_currency_is_kes(self):
        self.assertEqual(Money("1").currency, DEFAULT_CURRENCY)
        self.assertEqual(Money("1").currency, "KES")

    def test_currency_uppercased_and_validated(self):
        self.assertEqual(Money("1", "usd").currency, "USD")
        for bad in ("KE", "KESS", "K1S", ""):
            with self.assertRaises(MoneyError):
                Money("1", bad)

    def test_immutable(self):
        m = Money("5")
        with self.assertRaises(Exception):
            m.amount = Decimal("6")

    def test_zero_and_minor_units_roundtrip(self):
        self.assertTrue(Money.zero().is_zero)
        self.assertEqual(Money.from_minor_units(12_345).amount, Decimal("1.2345"))
        self.assertEqual(Money("1.2345").minor_units, 12_345)


class MoneyArithmeticTests(SimpleTestCase):
    def test_add_sub_neg_abs(self):
        self.assertEqual(Money("10") + Money("5"), Money("15"))
        self.assertEqual(Money("10") - Money("15"), Money("-5"))
        self.assertEqual(-Money("10"), Money("-10"))
        self.assertEqual(abs(Money("-10")), Money("10"))

    def test_scalar_multiplication(self):
        self.assertEqual(Money("100") * Decimal("0.025"), Money("2.5"))
        self.assertEqual(3 * Money("100"), Money("300"))

    def test_cannot_multiply_money_by_money(self):
        with self.assertRaises(MoneyError):
            Money("10") * Money("10")

    def test_cross_currency_arithmetic_rejected(self):
        with self.assertRaises(CurrencyMismatch):
            Money("10", "KES") + Money("10", "USD")
        with self.assertRaises(CurrencyMismatch):
            Money("10", "KES") - Money("10", "USD")

    def test_predicates_and_bool(self):
        self.assertTrue(Money("1").is_positive)
        self.assertTrue(Money("-1").is_negative)
        self.assertTrue(Money.zero().is_zero)
        self.assertFalse(bool(Money.zero()))
        self.assertTrue(bool(Money("0.0001")))


class MoneyOrderingTests(SimpleTestCase):
    def test_comparisons_same_currency(self):
        self.assertLess(Money("5"), Money("10"))
        self.assertGreaterEqual(Money("10"), Money("10"))
        self.assertEqual(Money("10"), Money("10.0000"))

    def test_comparison_cross_currency_raises(self):
        with self.assertRaises(CurrencyMismatch):
            Money("5", "KES") < Money("10", "USD")

    def test_equality_across_currency_is_false_not_error(self):
        # __eq__ stays total (safe for sets/dicts); only ordering checks currency.
        self.assertNotEqual(Money("10", "KES"), Money("10", "USD"))
        self.assertEqual(len({Money("10"), Money("10.0000")}), 1)


class MoneyAllocationTests(SimpleTestCase):
    def test_even_split_loses_no_units(self):
        parts = Money("10").split(3)
        self.assertEqual(sum(parts, Money.zero()), Money("10"))
        # 10.0000 / 3 -> two of 3.3333 and one 3.3334 (largest remainder)
        self.assertEqual(sorted(p.amount for p in parts),
                         [Decimal("3.3333"), Decimal("3.3333"), Decimal("3.3334")])

    def test_weighted_allocation_sums_exactly(self):
        parts = Money("100").allocate([1, 1, 1])
        self.assertEqual(sum(parts, Money.zero()), Money("100"))

    def test_allocation_preserves_currency(self):
        for p in Money("9", "USD").split(2):
            self.assertEqual(p.currency, "USD")

    def test_negative_amount_allocation(self):
        parts = Money("-10").split(3)
        self.assertEqual(sum(parts, Money.zero()), Money("-10"))

    def test_bad_weights_raise(self):
        with self.assertRaises(MoneyError):
            Money("10").allocate([])
        with self.assertRaises(MoneyError):
            Money("10").allocate([0, 0])
        with self.assertRaises(MoneyError):
            Money("10").allocate([-1, 2])


class MoneyDisplayTests(SimpleTestCase):
    def test_quantized_for_display_and_rails(self):
        self.assertEqual(Money("1234.5678").quantized(2), Decimal("1234.57"))
        self.assertEqual(Money("1234.5678").quantized(0), Decimal("1235"))

    def test_str_and_repr(self):
        self.assertEqual(str(Money("10", "KES")), "10.0000 KES")
        self.assertEqual(repr(Money("10")), "Money('10.0000', 'KES')")
