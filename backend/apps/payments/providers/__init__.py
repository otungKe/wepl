"""
PaymentProvider port — the rail-agnostic contract for moving money in and out.

The ledger and services speak only this interface; concrete rails (M-Pesa today,
card/bank/other MMOs tomorrow) live behind adapters and never leak their field
names upward. A FakeProvider implements the same contract so money-path tests run
with no network (ADR-0005).

Amounts are `Money`; results/events are normalised dataclasses. Each adapter is
responsible for translating to/from its rail's wire format.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal

from apps.ledger.money import Money


# ── Normalised results & events (rail-agnostic) ──────────────────────────────
@dataclass(frozen=True)
class CollectionResult:
    """Outcome of *initiating* a pay-in (e.g. STK push). The money has not
    arrived yet — settlement is confirmed later via a callback event."""
    accepted: bool
    provider_ref: str           # rail's correlation id (e.g. CheckoutRequestID)
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class PayoutResult:
    """Outcome of *initiating* a pay-out (e.g. B2C). Final success/failure
    arrives later via a callback event."""
    accepted: bool
    provider_ref: str           # rail's correlation id (e.g. ConversationID)
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class StatusResult:
    state: str                  # 'pending' | 'success' | 'failed' | 'unknown'
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class CallbackEvent:
    """A normalised inbound webhook, independent of the rail's field names.

    The posting layer consumes only this — never raw Daraja JSON.
    """
    kind: str                   # 'collection' | 'payout'
    success: bool
    provider_ref: str           # correlation id matching the initiate result
    result_desc: str = ''
    code: str = ''              # provider's native result code (string form)
    receipt: str | None = None  # rail receipt for a settled collection/payout
    amount: Decimal | None = None
    phone: str | None = None
    # Counterparty's registered M-Pesa name when the rail discloses it: the payer
    # for a C2B pay-in, the recipient for a B2C payout. STK Push does not return
    # a name, so this stays None there.
    counterparty_name: str | None = None
    raw: dict = field(default_factory=dict)


class PaymentProviderError(Exception):
    """Raised by adapters for unrecoverable rail errors."""


class PaymentProvider(ABC):
    """A payment rail. Implementations must be stateless and side-effect-free
    except for the network calls they make."""

    name: str = 'base'

    @abstractmethod
    def initiate_collection(
        self, *, phone: str, amount: Money, reference: str, description: str,
    ) -> CollectionResult:
        """Request money *from* a customer (pay-in)."""

    @abstractmethod
    def initiate_payout(
        self, *, phone: str, amount: Money, reference: str, remarks: str,
    ) -> PayoutResult:
        """Send money *to* a customer (pay-out)."""

    @abstractmethod
    def parse_callback(self, payload: dict, *, kind: str) -> CallbackEvent:
        """Translate a raw inbound webhook into a normalised CallbackEvent.

        ``kind`` is 'collection' or 'payout' (the endpoint that received it).
        """

    def query_status(self, *, provider_ref: str) -> StatusResult:
        """Poll the rail for a transaction's status. Optional — adapters that
        do not support it may leave this unimplemented."""
        raise NotImplementedError(f"{self.name} does not support query_status()")
