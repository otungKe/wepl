"""
Money — the single value object for monetary amounts in WEPL.

Standard (ADR-0003):
  * Storage precision is ``Decimal(max_digits=20, decimal_places=4)`` — matching
    the ledger's JournalLine.amount / AccountBalance columns.
  * Rounding is **banker's rounding** (``ROUND_HALF_EVEN``) applied only at the
    defined quantisation points here.
  * Every amount carries an explicit ISO-4217-style currency code (default KES).
    Cross-currency arithmetic is rejected — FX is a Phase 5 concern and must go
    through an explicit conversion, never an implicit one.

Use ``Money`` at service boundaries and when building journals so amounts are
always normalised and currency-safe. Bare ``Decimal`` math on money is the thing
this type exists to stop.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN, InvalidOperation
from typing import Iterable

# ── Standard constants ───────────────────────────────────────────────────────
DEFAULT_CURRENCY = "KES"
PLACES = 4                                   # ledger storage precision
ROUNDING = ROUND_HALF_EVEN                   # banker's rounding
_EXPONENT = Decimal(1).scaleb(-PLACES)       # Decimal('0.0001')
_MINOR_PER_UNIT = 10 ** PLACES               # 10_000 ledger-units per currency unit


class MoneyError(Exception):
    """Base class for money errors."""


class CurrencyMismatch(MoneyError):
    """Raised when an operation mixes two different currencies."""


def _coerce(value) -> Decimal:
    """Coerce a Decimal-like value to Decimal, going via str for floats so we
    never inherit binary floating-point error."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise MoneyError(f"Not a valid monetary amount: {value!r}") from exc


def quantize(value, places: int = PLACES, rounding: str = ROUNDING) -> Decimal:
    """Quantise a Decimal-coercible value to ``places`` using banker's rounding.

    This is the one rounding entry point — call it instead of ad-hoc
    ``.quantize()`` so the policy stays in a single place.
    """
    return _coerce(value).quantize(Decimal(1).scaleb(-places), rounding=rounding)


def _norm_currency(currency: str) -> str:
    c = (currency or "").strip().upper()
    if len(c) != 3 or not c.isalpha():
        raise MoneyError(f"Invalid currency code: {currency!r} (expected 3 letters)")
    return c


@dataclass(frozen=True)
class Money:
    """An immutable amount-plus-currency. Amount is normalised to PLACES dp."""

    amount: Decimal
    currency: str = DEFAULT_CURRENCY

    def __post_init__(self):
        object.__setattr__(self, "currency", _norm_currency(self.currency))
        object.__setattr__(self, "amount", quantize(self.amount))

    # ── Constructors ─────────────────────────────────────────────────────────
    @classmethod
    def zero(cls, currency: str = DEFAULT_CURRENCY) -> "Money":
        return cls(Decimal("0"), currency)

    @classmethod
    def from_minor_units(cls, units: int, currency: str = DEFAULT_CURRENCY) -> "Money":
        """Build from integer ledger minor units (1 unit = 10**-PLACES)."""
        return cls(Decimal(int(units)) / _MINOR_PER_UNIT, currency)

    # ── Internal helpers ─────────────────────────────────────────────────────
    def _check(self, other: "Money") -> None:
        if not isinstance(other, Money):
            raise MoneyError(f"Expected Money, got {type(other).__name__}")
        if other.currency != self.currency:
            raise CurrencyMismatch(
                f"Cannot combine {self.currency} and {other.currency}"
            )

    @property
    def minor_units(self) -> int:
        """Amount as an exact integer count of 10**-PLACES units."""
        return int((self.amount * _MINOR_PER_UNIT).to_integral_value(rounding=ROUNDING))

    # ── Arithmetic (currency-safe) ───────────────────────────────────────────
    def __add__(self, other: "Money") -> "Money":
        self._check(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._check(other)
        return Money(self.amount - other.amount, self.currency)

    def __neg__(self) -> "Money":
        return Money(-self.amount, self.currency)

    def __abs__(self) -> "Money":
        return Money(abs(self.amount), self.currency)

    def __mul__(self, scalar) -> "Money":
        """Multiply by a dimensionless scalar (e.g. a fee rate or a count)."""
        if isinstance(scalar, Money):
            raise MoneyError("Cannot multiply Money by Money")
        return Money(self.amount * _coerce(scalar), self.currency)

    __rmul__ = __mul__

    # ── Predicates ───────────────────────────────────────────────────────────
    @property
    def is_zero(self) -> bool:
        return self.amount == 0

    @property
    def is_positive(self) -> bool:
        return self.amount > 0

    @property
    def is_negative(self) -> bool:
        return self.amount < 0

    def __bool__(self) -> bool:
        return not self.is_zero

    # ── Ordering (currency-checked) ──────────────────────────────────────────
    def __lt__(self, other: "Money") -> bool:
        self._check(other)
        return self.amount < other.amount

    def __le__(self, other: "Money") -> bool:
        self._check(other)
        return self.amount <= other.amount

    def __gt__(self, other: "Money") -> bool:
        self._check(other)
        return self.amount > other.amount

    def __ge__(self, other: "Money") -> bool:
        self._check(other)
        return self.amount >= other.amount

    # ── Allocation / splitting (loses no minor units) ────────────────────────
    def allocate(self, weights: Iterable) -> list["Money"]:
        """Split this amount across ``weights`` so the parts sum back exactly to
        the original (largest-remainder method on integer minor units)."""
        weights = [_coerce(w) for w in weights]
        if not weights:
            raise MoneyError("allocate() needs at least one weight")
        if any(w < 0 for w in weights):
            raise MoneyError("allocate() weights must be non-negative")
        total_weight = sum(weights)
        if total_weight <= 0:
            raise MoneyError("allocate() weights must sum to a positive value")

        total = self.minor_units
        sign = -1 if total < 0 else 1
        total_abs = abs(total)

        raw = [total_abs * w / total_weight for w in weights]
        floors = [int(r) for r in raw]
        remainder = total_abs - sum(floors)
        # hand out the leftover units to the largest fractional remainders
        order = sorted(range(len(weights)), key=lambda i: raw[i] - floors[i], reverse=True)
        for i in range(remainder):
            floors[order[i]] += 1
        return [Money.from_minor_units(sign * u, self.currency) for u in floors]

    def split(self, n: int) -> list["Money"]:
        """Split evenly into ``n`` parts, distributing leftover minor units."""
        if n <= 0:
            raise MoneyError("split() needs a positive part count")
        return self.allocate([1] * n)

    # ── Display ──────────────────────────────────────────────────────────────
    def quantized(self, places: int) -> Decimal:
        """Return the amount rounded to ``places`` (e.g. 2 for display, 0 for
        M-Pesa which transacts whole shillings). Does not mutate this Money."""
        return quantize(self.amount, places)

    def __str__(self) -> str:
        return f"{self.amount} {self.currency}"

    def __repr__(self) -> str:
        return f"Money('{self.amount}', '{self.currency}')"
