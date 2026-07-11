"""
M-Pesa (Safaricom Daraja) adapter — the first PaymentProvider implementation.

All Daraja-specific wire details (STK push, B2C, and the field names in their
callbacks) are confined to this module. Nothing above the provider layer should
import Daraja field names.
"""
from __future__ import annotations

import logging

from apps.ledger.money import Money
from apps.mpesa.services import MpesaService

from . import (
    CallbackEvent, CollectionResult, PaymentProvider, PaymentProviderError, PayoutResult,
    StatusResult,
)

logger = logging.getLogger(__name__)


def _to_int_amount(amount: Money) -> int:
    """M-Pesa transacts whole shillings."""
    return int(amount.quantized(0))


def _public_name(public: str | None) -> str | None:
    """Extract the name from a Daraja "PublicName" field, e.g.
    ``"254708374149 - JOHN DOE"`` → ``"JOHN DOE"``. Returns None when absent or
    when only the number (no name) is present."""
    if not public:
        return None
    name = public.split(' - ', 1)[-1].strip() if ' - ' in public else ''
    return name or None


class MpesaProvider(PaymentProvider):
    name = 'mpesa'

    def initiate_collection(self, *, phone, amount: Money, reference, description) -> CollectionResult:
        resp = MpesaService.stk_push(
            phone_number=phone, amount=_to_int_amount(amount),
            account_ref=reference, description=description,
        )
        # Daraja: ResponseCode "0" means the STK request was accepted.
        accepted = str(resp.get('ResponseCode', '')) == '0'
        return CollectionResult(
            accepted=accepted,
            provider_ref=resp.get('CheckoutRequestID', ''),
            raw=resp,
        )

    def initiate_payout(self, *, phone, amount: Money, reference, remarks) -> PayoutResult:
        resp = MpesaService.b2c_payment(
            phone_number=phone, amount=_to_int_amount(amount),
            reference=reference, remarks=remarks,
        )
        accepted = str(resp.get('ResponseCode', '')) == '0'
        return PayoutResult(
            accepted=accepted,
            provider_ref=resp.get('ConversationID', ''),
            raw=resp,
        )

    def query_status(self, *, provider_ref: str) -> StatusResult:
        resp = MpesaService.query_stk_status(provider_ref)
        code = str(resp.get('ResultCode', ''))
        if code == '0':
            state = 'success'
        elif code == '':
            state = 'pending'      # still under processing / no definitive result yet
        else:
            state = 'failed'
        return StatusResult(state=state, raw=resp)

    def request_payout_result(self, *, provider_ref: str) -> None:
        """Fire a Daraja B2C Transaction Status Query so Safaricom re-delivers a
        stuck payout's final result to the B2C ResultURL. Best-effort and
        side-effect-only; the definitive outcome arrives asynchronously via the
        callback, so this returns nothing."""
        if not provider_ref:
            return None
        import requests
        from django.conf import settings
        try:
            token = MpesaService._get_access_token()
            payload = {
                "Initiator":          settings.MPESA_B2C_INITIATOR_NAME,
                "SecurityCredential": settings.MPESA_B2C_SECURITY_CREDENTIAL,
                "CommandID":          "TransactionStatusQuery",
                "TransactionID":      provider_ref,
                "PartyA":             settings.MPESA_SHORTCODE,
                "IdentifierType":     "4",
                "ResultURL":          settings.MPESA_B2C_RESULT_URL,
                "QueueTimeOutURL":    settings.MPESA_B2C_TIMEOUT_URL,
                "Remarks":            f"Status query for {provider_ref}",
                "Occasion":           "",
            }
            resp = requests.post(
                f"{settings.MPESA_BASE_URL}/mpesa/transactionstatus/v1/query",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
                timeout=15,
            )
            resp.raise_for_status()
        except Exception as exc:
            logger.warning(
                "request_payout_result: re-query failed for %s (%s)", provider_ref, exc
            )
        return None

    def parse_callback(self, payload: dict, *, kind: str) -> CallbackEvent:
        if kind == 'collection':
            return self._parse_stk_callback(payload)
        if kind == 'payout':
            return self._parse_b2c_result(payload)
        raise PaymentProviderError(f"Unknown callback kind: {kind!r}")

    # ── Daraja-specific parsing (kept private to this adapter) ────────────────
    @staticmethod
    def _parse_stk_callback(payload: dict) -> CallbackEvent:
        cb = (payload.get('Body', {}) or {}).get('stkCallback', {}) or {}
        result_code = cb.get('ResultCode')
        success = str(result_code) == '0'
        receipt = amount = phone = None
        if success:
            items = (cb.get('CallbackMetadata', {}) or {}).get('Item', []) or []
            meta = {i.get('Name'): i.get('Value') for i in items}
            receipt = meta.get('MpesaReceiptNumber')
            amount = meta.get('Amount')
            phone = str(meta.get('PhoneNumber')) if meta.get('PhoneNumber') else None
        return CallbackEvent(
            kind='collection',
            success=success,
            provider_ref=cb.get('CheckoutRequestID', ''),
            result_desc=cb.get('ResultDesc', ''),
            code='' if result_code is None else str(result_code),
            receipt=receipt,
            amount=amount,
            phone=phone,
            raw=payload,
        )

    @staticmethod
    def _parse_b2c_result(payload: dict) -> CallbackEvent:
        result = (payload.get('Result', {}) or {})
        result_code = result.get('ResultCode')
        success = str(result_code) == '0'
        receipt = name = None
        if success:
            params = (result.get('ResultParameters', {}) or {}).get('ResultParameter', []) or []
            meta = {p.get('Key'): p.get('Value') for p in params}
            receipt = meta.get('TransactionReceipt') or meta.get('TransactionID')
            # Daraja returns the recipient as "2547… - JOHN DOE"; keep the name.
            name = _public_name(meta.get('ReceiverPartyPublicName'))
        return CallbackEvent(
            kind='payout',
            success=success,
            provider_ref=result.get('ConversationID') or result.get('OriginatorConversationID') or '',
            result_desc=result.get('ResultDesc', ''),
            code='' if result_code is None else str(result_code),
            receipt=receipt,
            counterparty_name=name,
            raw=payload,
        )
