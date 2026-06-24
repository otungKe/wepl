"""Provider-agnostic payment lifecycle (ADR-0014).

PaymentService owns the PaymentIntent state machine. Provider adapters / the
mpesa chokepoints call ``record_initiation`` when a collection/payout is accepted
and ``resolve`` when the provider's callback lands — speaking only normalised
terms (provider name, direction, provider_ref), never rail field names.

All methods are idempotent and best-effort-safe: callers wrap them so a payment
bookkeeping hiccup can never break the actual money path (the ledger remains the
source of truth).
"""
import logging

from django.db import transaction
from django.utils import timezone

from .models import PaymentIntent

logger = logging.getLogger(__name__)


class PaymentService:

    @staticmethod
    def record_initiation(*, provider, direction, amount, idempotency_key,
                          provider_ref='', currency='KES', financial_transaction=None,
                          op_type='', initiated_by=None, tenant_id=None, metadata=None):
        """Record (idempotently) that a payment was initiated and accepted by the
        provider. Returns the PaymentIntent (PENDING)."""
        intent, _ = PaymentIntent.objects.get_or_create(
            idempotency_key=idempotency_key,
            defaults={
                'provider': provider,
                'direction': direction,
                'amount': amount,
                'currency': currency,
                'provider_ref': provider_ref or '',
                'financial_transaction': financial_transaction,
                'op_type': op_type or '',
                'initiated_by': initiated_by if getattr(initiated_by, 'pk', None) else None,
                'tenant_id': tenant_id,
                'metadata': metadata or {},
                'status': PaymentIntent.Status.PENDING,
            },
        )
        return intent

    @staticmethod
    @transaction.atomic
    def resolve(*, provider, provider_ref, success, receipt='', failure_reason='',
                metadata=None):
        """Settle the pending intent for (provider, provider_ref). Idempotent: a
        terminal intent (or a missing one) is a no-op. Returns the intent or None."""
        if not provider_ref:
            return None
        intent = (
            PaymentIntent.objects
            .select_for_update()
            .filter(provider=provider, provider_ref=provider_ref,
                    status=PaymentIntent.Status.PENDING)
            .order_by('-created_at')
            .first()
        )
        if intent is None:
            return None
        target = (PaymentIntent.Status.SUCCEEDED if success
                  else PaymentIntent.Status.FAILED)
        PaymentService._transition(intent, target, receipt=receipt,
                                   failure_reason=failure_reason, metadata=metadata)
        return intent

    @staticmethod
    def mark_reversed(intent, *, reason=''):
        """Move a SUCCEEDED intent to REVERSED (e.g. a refund)."""
        PaymentService._transition(intent, PaymentIntent.Status.REVERSED,
                                   failure_reason=reason)
        return intent

    @staticmethod
    def _transition(intent, target, *, receipt='', failure_reason='', metadata=None):
        allowed = PaymentIntent.VALID_TRANSITIONS.get(intent.status, frozenset())
        if target not in allowed:
            logger.warning("PaymentIntent %s: illegal transition %s → %s",
                           intent.id, intent.status, target)
            return
        intent.status = target
        fields = ['status', 'updated_at']
        if receipt:
            intent.receipt = receipt[:64]; fields.append('receipt')
        if failure_reason:
            intent.failure_reason = failure_reason; fields.append('failure_reason')
        if metadata:
            intent.metadata = {**(intent.metadata or {}), **metadata}; fields.append('metadata')
        intent.updated_at = timezone.now()
        intent.save(update_fields=fields)
