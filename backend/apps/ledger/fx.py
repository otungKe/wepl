"""
Foreign-exchange helpers.

Currency conversion is always **explicit** — there is no implicit cross-currency
arithmetic anywhere (``Money`` rejects it). Rates come from the effective-dated
``ExchangeRate`` table so any past conversion is reproducible.

Cross-currency movements are posted as a single journal that balances **per
currency** (enforced by post_journal): each currency leg is squared via a
per-currency FX clearing account. Realised FX gain/loss is recognised when those
clearing positions are later revalued/netted against an FX gain/loss account.
"""
from __future__ import annotations

from decimal import Decimal

from django.utils import timezone

from .models import ExchangeRate, JournalLine
from .money import Money, quantize
from .posting import Line


class RateNotFound(Exception):
    """No exchange rate available for the requested pair / date."""


def get_rate(base: str, quote: str, at=None) -> Decimal:
    """Return the rate effective at ``at`` (default now) for 1 base = rate × quote.

    Falls back to the inverse pair (1/rate) when only the opposite direction is
    stored. Same-currency conversions return 1.
    """
    base, quote = base.upper(), quote.upper()
    if base == quote:
        return Decimal('1')
    at = at or timezone.now()

    direct = (
        ExchangeRate.objects
        .filter(base_currency=base, quote_currency=quote, effective_at__lte=at)
        .order_by('-effective_at').first()
    )
    if direct is not None:
        return direct.rate

    inverse = (
        ExchangeRate.objects
        .filter(base_currency=quote, quote_currency=base, effective_at__lte=at)
        .order_by('-effective_at').first()
    )
    if inverse is not None and inverse.rate != 0:
        return Decimal('1') / inverse.rate

    raise RateNotFound(f"No exchange rate for {base}->{quote} at {at.isoformat()}")


def convert(money: Money, to_currency: str, *, at=None, rate: Decimal | None = None) -> Money:
    """Convert ``money`` into ``to_currency`` using an explicit rate.

    Pass ``rate`` to pin it (e.g. the rate quoted by the rail), otherwise it is
    resolved from the ExchangeRate table effective at ``at``.
    """
    to_currency = to_currency.upper()
    if money.currency == to_currency:
        return money
    r = rate if rate is not None else get_rate(money.currency, to_currency, at=at)
    return Money(quantize(money.amount * r), to_currency)


def conversion_lines(*, source_account, source_clearing, dest_account, dest_clearing,
                     source_money: Money, to_currency: str, at=None, rate: Decimal | None = None,
                     note: str = '') -> list[Line]:
    """Build a per-currency-balanced cross-currency journal.

    Moves ``source_money`` out of ``source_account`` into ``dest_account`` in
    ``to_currency``. Each currency leg squares against its FX clearing account, so
    the journal balances per currency and ``post_journal`` accepts it.

    Accounts must match currencies: source_account/source_clearing in
    ``source_money.currency``; dest_account/dest_clearing in ``to_currency``.
    """
    dest = convert(source_money, to_currency, at=at, rate=rate)
    D, C = JournalLine.Direction.DEBIT, JournalLine.Direction.CREDIT
    return [
        # Source currency leg (balances in source_money.currency)
        Line(account=source_account,  direction=C, amount=source_money.amount, note=note),
        Line(account=source_clearing, direction=D, amount=source_money.amount, note=note),
        # Destination currency leg (balances in to_currency)
        Line(account=dest_account,    direction=D, amount=dest.amount, note=note),
        Line(account=dest_clearing,   direction=C, amount=dest.amount, note=note),
    ]
