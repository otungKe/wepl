"""Provider-agnostic payment lifecycle (ADR-0014).

PaymentService drives the PaymentIntent state machine (the transitions themselves
are encapsulated on the model — ``PaymentIntent.transition_to``). Provider adapters
/ the mpesa chokepoints call ``record_initiation`` when a collection/payout is
accepted and ``resolve`` when the provider's callback lands — speaking only
normalised terms (provider name, direction, provider_ref), never rail field names.
``record_provider_event`` durably captures the raw callback for audit/replay.

All methods are idempotent and best-effort-safe: callers wrap them so a payment
bookkeeping hiccup can never break the actual money path (the ledger remains the
source of truth).
"""
import logging

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import TransitionError

from .models import PaymentIntent, ProviderEvent

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
                'initiated_at': timezone.now(),
            },
        )
        return intent

    @staticmethod
    @transaction.atomic
    def resolve(*, provider, provider_ref, success, receipt='',
                failure_code='', failure_message='', metadata=None, event_time=None):
        """Settle the pending intent for (provider, provider_ref). Idempotent: a
        terminal intent (or a missing one) is a no-op. Returns the intent or None.

        A receipt already seen on another intent is not stored (the DB enforces
        receipt uniqueness); instead a ``duplicate_receipt`` drift is opened and
        the status is still settled — losing the duplicate receipt, not the money
        truth."""
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

        # Stamp when the settling callback was received (SLA / late-callback checks).
        now = timezone.now()
        PaymentIntent.objects.filter(pk=intent.pk).update(callback_received_at=now)
        intent.callback_received_at = now

        # Receipt uniqueness: a receipt seen elsewhere is a reconciliation signal,
        # not something to store twice. Settle without it and flag the drift.
        if success and receipt and PaymentIntent.objects.filter(
                receipt=receipt).exclude(pk=intent.pk).exists():
            _open_drift('duplicate_receipt', 'payment_intent', intent.id,
                        f"receipt {receipt} already recorded on another intent")
            logger.warning("PaymentIntent %s: duplicate receipt %s — settling without it",
                           intent.id, receipt)
            receipt = ''

        target = (PaymentIntent.Status.SUCCEEDED if success
                  else PaymentIntent.Status.FAILED)
        try:
            intent.transition_to(
                target, receipt=receipt, failure_code=failure_code,
                failure_message=failure_message, metadata=metadata,
                completed_at=event_time)
        except TransitionError:
            # Lost a concurrent settle, or an illegal edge — bookkeeping is
            # best-effort and must never break the money path.
            logger.warning("PaymentIntent %s: resolve transition to %s skipped",
                           intent.id, target)
            return intent
        return intent

    @staticmethod
    def mark_reversed(intent, *, failure_code='', reason=''):
        """Move a SUCCEEDED intent to REVERSED (e.g. a refund). No-op (logged) if
        the intent isn't in a reversible state."""
        try:
            intent.transition_to(PaymentIntent.Status.REVERSED,
                                 failure_code=failure_code, failure_message=reason)
        except TransitionError:
            logger.warning("PaymentIntent %s: cannot reverse from %s — no-op",
                           intent.id, intent.status)
        return intent

    @staticmethod
    def record_provider_event(*, provider, event_type, payload, provider_ref='',
                              payment_intent=None, signature_verified=False,
                              provider_event_id=''):
        """Append a raw provider callback/event to the immutable history. Best-effort
        and idempotent on ``provider_event_id`` — a re-delivered event is dropped.
        Returns the ProviderEvent or None."""
        from django.db import IntegrityError
        try:
            # Own savepoint so a duplicate (IntegrityError) rolls back cleanly
            # without poisoning the caller's transaction.
            with transaction.atomic():
                return ProviderEvent.objects.create(
                    provider=provider, event_type=event_type, payload=payload or {},
                    provider_ref=provider_ref or '', payment_intent=payment_intent,
                    signature_verified=signature_verified,
                    provider_event_id=provider_event_id or '')
        except IntegrityError:
            logger.info("ProviderEvent for %s/%s already recorded — skipping duplicate",
                        provider, provider_event_id)
            return None
        except Exception:
            logger.exception("record_provider_event failed for %s/%s", provider, event_type)
            return None


def _open_drift(kind, subject_type, subject_id, detail):
    """Open a reconciliation drift (deferred import avoids a cycle)."""
    from .reconciliation import _open_drift as _open
    return _open(kind, subject_type, subject_id, detail)
