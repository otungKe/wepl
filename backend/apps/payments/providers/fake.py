"""
FakeProvider — an in-memory PaymentProvider for hermetic tests and the sandbox.

Records every call and returns deterministic, normalised results with no network.
Helpers build matching CallbackEvents so a test can simulate the full
initiate → callback lifecycle.
"""
from __future__ import annotations

import itertools

from apps.ledger.money import Money

from . import CallbackEvent, CollectionResult, PaymentProvider, PayoutResult, StatusResult


class FakeProvider(PaymentProvider):
    name = 'fake'

    def __init__(self, *, accept: bool = True):
        self.accept = accept
        self.collections: list[dict] = []
        self.payouts: list[dict] = []
        self._seq = itertools.count(1)

    def initiate_collection(self, *, phone, amount: Money, reference, description) -> CollectionResult:
        ref = f"FAKE-COL-{next(self._seq)}"
        self.collections.append({
            'provider_ref': ref, 'phone': phone, 'amount': amount, 'reference': reference,
        })
        return CollectionResult(accepted=self.accept, provider_ref=ref, raw={'reference': reference})

    def initiate_payout(self, *, phone, amount: Money, reference, remarks) -> PayoutResult:
        ref = f"FAKE-PAY-{next(self._seq)}"
        self.payouts.append({
            'provider_ref': ref, 'phone': phone, 'amount': amount, 'reference': reference,
        })
        return PayoutResult(accepted=self.accept, provider_ref=ref, raw={'reference': reference})

    def parse_callback(self, payload: dict, *, kind: str) -> CallbackEvent:
        return CallbackEvent(
            kind=kind,
            success=bool(payload.get('success', True)),
            provider_ref=payload.get('provider_ref', ''),
            result_desc=payload.get('result_desc', ''),
            code=payload.get('code', ''),
            receipt=payload.get('receipt'),
            amount=payload.get('amount'),
            phone=payload.get('phone'),
            raw=payload,
        )

    def query_status(self, *, provider_ref: str) -> StatusResult:
        return StatusResult(state='success', raw={'provider_ref': provider_ref})

    # ── Test helpers ─────────────────────────────────────────────────────────
    def make_collection_callback(self, provider_ref, *, success=True, receipt='FAKE-RCPT',
                                 amount=None, phone=None) -> CallbackEvent:
        return CallbackEvent(
            kind='collection', success=success, provider_ref=provider_ref,
            receipt=receipt if success else None, amount=amount, phone=phone,
        )

    def make_payout_callback(self, provider_ref, *, success=True, receipt='FAKE-RCPT') -> CallbackEvent:
        return CallbackEvent(
            kind='payout', success=success, provider_ref=provider_ref,
            receipt=receipt if success else None,
        )
