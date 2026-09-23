"""Money-activity read projection (ADR-0030).

A read-only, unified view of one money movement, reconstructed from the ledger and
the payment rail. This is the reporting substitute that lets ``FinancialTransaction``
dissolve: callers migrate onto this seam now, and its internals move off FT (onto
the ``JournalEntry`` idempotency_key + ``PaymentIntent``) across ADR-0030's later
slices **without changing this API**.

Today it is anchored on a ``FinancialTransaction`` and reads the rail dimension
from the linked ``PaymentIntent``, which is the only source of it: FT's
``mpesa_*`` columns are gone (ADR-0030), their values carried into intents by
``payments.0008``.

It is a **view, never a source of truth** (ADR-0002): nothing here is stored.

It lives in ``apps.payments`` rather than ``apps.ledger`` because the rail
dimension is the payments layer's business and the ledger must not import it.
``apps.payments`` already depends on ``apps.ledger``; the reverse edge is the one
that has to stay gone.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .models import PaymentIntent


@dataclass(frozen=True)
class RailInfo:
    """The external-rail dimension of a movement (from PaymentIntent, ADR-0014)."""
    provider: str = ""
    direction: str = ""            # PaymentIntent.Direction ('collection' | 'payout')
    status: str = ""               # PaymentIntent.Status
    checkout_id: str = ""          # STK CheckoutRequestID (collection correlation id)
    conversation_id: str = ""      # B2C ConversationID (payout correlation id)
    receipt: str = ""              # provider receipt (e.g. M-Pesa receipt)

    @property
    def has_rail(self) -> bool:
        return bool(self.checkout_id or self.conversation_id or self.receipt)


@dataclass(frozen=True)
class MoneyActivity:
    """The unified view of a single money movement."""
    reference: str                 # canonical handle, e.g. WEPL-TXN-000001
    op_type: str
    amount: Decimal
    state: str                     # movement state (FT state today; derived later)
    recipient_phone: str
    counterparty_name: str
    context_type: str
    context_id: int | None
    rail: RailInfo = field(default_factory=RailInfo)


def rail_for(ft) -> RailInfo:
    """Rail info from the movement's linked PaymentIntent.

    A movement with no intent never touched a rail (an internal reallocation, a
    surplus distribution), and correctly reports an empty ``RailInfo``.

    Uses ``.all()`` and picks the latest intent in Python rather than
    ``.order_by(...).first()``, so a caller that has done
    ``prefetch_related('payment_intents')`` hits the prefetch cache instead of
    issuing a query per row (an ``order_by`` on the related manager would bypass
    it). Without a prefetch this is still a single query.
    """
    intents = list(ft.payment_intents.all())
    intent = max(intents, key=lambda i: i.pk) if intents else None
    if intent is None:
        return RailInfo()

    # The correlation id means different things by direction: a CheckoutRequestID
    # going in, a ConversationID going out. One field on the intent, two names
    # here, because that is what operators and Safaricom call them.
    is_payout = intent.direction == PaymentIntent.Direction.PAYOUT
    return RailInfo(
        provider=intent.provider,
        direction=intent.direction,
        status=intent.status,
        checkout_id="" if is_payout else intent.provider_ref,
        conversation_id=intent.provider_ref if is_payout else "",
        receipt=intent.receipt or "",
    )


def for_financial_transaction(ft) -> MoneyActivity:
    """Build the money-activity view for one FinancialTransaction."""
    return MoneyActivity(
        reference=ft.reference,
        op_type=ft.op_type,
        amount=ft.amount,
        state=ft.state,
        recipient_phone=ft.recipient_phone or "",
        counterparty_name=ft.counterparty_name or "",
        context_type=ft.context_type or "",
        context_id=ft.context_id,
        rail=rail_for(ft),
    )


def financial_transaction_for_ref(provider_ref: str, *, provider: str = ""):
    """The FinancialTransaction a rail correlation id belongs to, via its intent.

    The reverse of ``rail_for``: a callback arrives carrying only the rail's own
    id, and the movement it settles has to be found from it. The link lives on
    ``PaymentIntent.financial_transaction`` (ADR-0014), which is the only place
    it lives now that FT's ``mpesa_conversation_id`` is gone (ADR-0030).

    Returns None when nothing matches — a callback for a movement this system
    never initiated.
    """
    if not provider_ref:
        return None

    intents = PaymentIntent.objects.filter(
        provider_ref=provider_ref, financial_transaction__isnull=False)
    if provider:
        intents = intents.filter(provider=provider)
    intent = intents.select_related('financial_transaction').order_by('-pk').first()
    return intent.financial_transaction if intent is not None else None
