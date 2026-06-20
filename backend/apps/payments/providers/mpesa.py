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
)

logger = logging.getLogger(__name__)


def _to_int_amount(amount: Money) -> int:
    """M-Pesa transacts whole shillings."""
    return int(amount.quantized(0))


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
        receipt = None
        if success:
            params = (result.get('ResultParameters', {}) or {}).get('ResultParameter', []) or []
            meta = {p.get('Key'): p.get('Value') for p in params}
            receipt = meta.get('TransactionReceipt')
        return CallbackEvent(
            kind='payout',
            success=success,
            provider_ref=result.get('ConversationID', ''),
            result_desc=result.get('ResultDesc', ''),
            receipt=receipt,
            raw=payload,
        )
