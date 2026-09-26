"""Starting a collection (pay-in) on whichever rail the provider registry resolves.

The *domain* decides what is being paid for — which contribution, welfare fund,
shares fund or advance, and whether the payer is allowed to pay at all. That
decision lives in ``apps.contributions``. Everything after it is bookkeeping this
layer owns: ask the provider to collect, record the rail request, and open the
provider-agnostic ``PaymentIntent`` (ADR-0014).

Keeping the split here is what lets ``apps.payments`` stay below the domain: the
caller passes fund *ids*, never fund objects, so nothing in this app imports
``apps.contributions`` (ADR-0033).
"""
import logging
import re
from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction

logger = logging.getLogger(__name__)

# Canonical Kenyan MSISDN after normalisation: 2547XXXXXXXX / 2541XXXXXXXX.
_KE_MSISDN = re.compile(r"^254(7|1)\d{8}$")


class CollectionUnavailable(Exception):
    """The provider could not be reached at all — a bad gateway, not a refusal."""


@dataclass(frozen=True)
class CollectionStart:
    """The outcome of asking a provider to collect."""
    accepted: bool
    provider_ref: str = ""
    error: str = ""


def normalized_msisdn(raw: str) -> str | None:
    """Return *raw* as a canonical Kenyan MSISDN, or None if it is not one.

    Normalisation is the rail client's, so the number we validate is exactly the
    number Daraja is handed.
    """
    from apps.mpesa.services import normalize_msisdn

    phone = normalize_msisdn(raw)
    return phone if _KE_MSISDN.match(phone) else None


def start_collection(
    *,
    user,
    phone: str,
    amount: Decimal,
    reference: str,
    description: str,
    payment_type: str,
    contribution_id=None,
    welfare_fund_id=None,
    shares_fund_id=None,
    advance_id=None,
) -> CollectionStart:
    """Ask the provider to collect *amount* from *phone*, and record the attempt.

    Raises ``CollectionUnavailable`` when the provider call itself fails; returns
    an unaccepted ``CollectionStart`` when the provider answers and refuses.
    """
    from apps.ledger.money import Money
    from .providers.registry import get_provider

    try:
        result = get_provider().initiate_collection(
            phone=phone,
            amount=Money(str(amount)),
            reference=reference,
            description=description,
        )
    except Exception as exc:
        logger.exception("STK push failed")
        raise CollectionUnavailable(str(exc)) from exc

    if not result.accepted:
        return CollectionStart(
            accepted=False,
            error=result.raw.get("errorMessage", "STK push failed"),
        )

    # The intent is what settles the pay-in now (``purpose``/``subject_ref`` are
    # read back when the callback lands), so it is written with the rail record
    # in one transaction rather than best-effort afterwards: a pay-in with a
    # rail record and no intent would have nowhere to route its money.
    subject_id = {
        "welfare": welfare_fund_id,
        "shares": shares_fund_id,
        "advance_repayment": advance_id,
    }.get(payment_type, contribution_id)

    with transaction.atomic():
        _record_collection(
            user=user, phone=phone, amount=amount, payment_type=payment_type,
            contribution_id=contribution_id, welfare_fund_id=welfare_fund_id,
            shares_fund_id=shares_fund_id, advance_id=advance_id,
            subject_id=subject_id, result=result,
        )

    return CollectionStart(accepted=True, provider_ref=result.provider_ref)


def _record_collection(*, user, phone, amount, payment_type, contribution_id,
                       welfare_fund_id, shares_fund_id, advance_id, subject_id,
                       result) -> None:
    from apps.mpesa.models import MpesaSTKRequest
    from apps.mpesa.services import normalize_msisdn
    from .models import PaymentIntent
    from .providers.registry import get_provider
    from .services import PaymentService

    MpesaSTKRequest.objects.create(
        user=user,
        payment_type=payment_type,
        contribution_id=contribution_id,
        welfare_fund_id=welfare_fund_id,
        shares_fund_id=shares_fund_id,
        advance_id=advance_id,
        phone_number=normalize_msisdn(phone),
        amount=amount,
        checkout_request_id=result.provider_ref,
        merchant_request_id=result.raw.get("MerchantRequestID", ""),
    )

    PaymentService.record_initiation(
        provider=get_provider().name,
        direction=PaymentIntent.Direction.COLLECTION,
        amount=amount,
        idempotency_key=f"pi-collect-{result.provider_ref}",
        provider_ref=result.provider_ref,
        op_type=payment_type,
        initiated_by=user,
        metadata={"payment_type": payment_type},
        purpose=payment_type,
        subject_ref=str(subject_id) if subject_id is not None else "",
    )
