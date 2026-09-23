"""Backfill a PaymentIntent for every payout that only lived in FT's columns.

ADR-0030 makes ``PaymentIntent`` authoritative for the rail dimension, which is
what lets ``FinancialTransaction``'s ``mpesa_conversation_id`` /
``mpesa_receipt`` / ``mpesa_checkout_id`` be dropped in the next slice. Before
the columns can go, the data in them has to exist in its new home — additive
first (P-7/E-2), so the drop loses nothing.

Those columns are written on the **payout path only**: the dispatch stamps
``mpesa_conversation_id`` and the B2C result stamps ``mpesa_receipt``
(``mpesa_checkout_id`` was never written by any code path). Collection FTs have
all three NULL, so there is nothing to carry forward on that side — their
coverage gap is a separate concern, measured by ``payments.coverage`` and not
a blocker for this drop.

Two cases per FT:

* an intent already correlates (same provider ref or receipt) but was never
  linked — attach it, no data invented;
* no intent exists — mint one from the columns, using the same FT-keyed
  idempotency key the live dispatch path uses so the two can never collide.

Re-runnable: FTs that already have a linked payout intent are skipped, and a
row that would violate the provider-ref or receipt uniqueness constraints is
reported rather than forced.
"""
from django.db import migrations
from django.db.models import Q

PAYOUT = 'payout'
SUCCEEDED, FAILED, PENDING, REVERSED = 'succeeded', 'failed', 'pending', 'reversed'

# FT.state → PaymentIntent.status. FT's PROCESSING and PENDING are both "the
# rail has not answered yet" as far as the intent is concerned.
_STATUS_FOR_STATE = {
    'SUCCESS': SUCCEEDED,
    'FAILED': FAILED,
    'REVERSED': REVERSED,
    'PENDING': PENDING,
    'PROCESSING': PENDING,
}


def backfill(apps, schema_editor):
    FinancialTransaction = apps.get_model('ledger', 'FinancialTransaction')
    PaymentIntent = apps.get_model('payments', 'PaymentIntent')

    has_rail = (
        Q(mpesa_conversation_id__isnull=False) & ~Q(mpesa_conversation_id='')
        | Q(mpesa_receipt__isnull=False) & ~Q(mpesa_receipt='')
        | Q(mpesa_checkout_id__isnull=False) & ~Q(mpesa_checkout_id='')
    )
    candidates = (FinancialTransaction.objects
                  .filter(has_rail)
                  .exclude(payment_intents__direction=PAYOUT)
                  .order_by('pk'))

    linked = minted = 0
    for ft in candidates.iterator(chunk_size=500):
        ref = (ft.mpesa_conversation_id or ft.mpesa_checkout_id or '').strip()
        receipt = (ft.mpesa_receipt or '').strip()

        # 1. An unlinked intent that already correlates — attach, never duplicate.
        match = None
        if ref:
            match = PaymentIntent.objects.filter(
                provider_ref=ref, financial_transaction__isnull=True).first()
        if match is None and receipt:
            match = PaymentIntent.objects.filter(
                receipt=receipt, financial_transaction__isnull=True).first()
        if match is not None:
            match.financial_transaction = ft
            match.save(update_fields=['financial_transaction'])
            linked += 1
            continue

        # 2. Nothing correlates — mint the intent the dispatch would have written.
        #    Skip a value that another intent already owns rather than break the
        #    uniqueness constraints; the ref/receipt is then reported by the
        #    coverage report as a mismatch for a human to look at.
        if ref and PaymentIntent.objects.filter(provider_ref=ref).exists():
            ref = ''
        if receipt and PaymentIntent.objects.filter(receipt=receipt).exists():
            receipt = ''

        PaymentIntent.objects.update_or_create(
            idempotency_key=f'pi-payout-{ft.pk}',
            defaults={
                'provider': 'mpesa',
                'direction': PAYOUT,
                'status': _STATUS_FOR_STATE.get(ft.state, PENDING),
                'amount': ft.amount,
                'currency': 'KES',
                'provider_ref': ref,
                'receipt': receipt,
                'financial_transaction': ft,
                'op_type': ft.op_type or '',
                'tenant_id': ft.tenant_id,
                'initiated_by_id': ft.initiated_by_id,
                'initiated_at': ft.created_at,
                'metadata': {'backfilled_from': 'financial_transaction.mpesa_*'},
            },
        )
        minted += 1

    if linked or minted:
        print(f"  backfilled payout intents: {linked} linked, {minted} minted")


def unbackfill(apps, schema_editor):
    """Drop only the intents this migration minted. Intents it merely *linked*
    existed before and are left alone — unlinking them would lose a correlation
    the backfill discovered, not restore a prior state."""
    PaymentIntent = apps.get_model('payments', 'PaymentIntent')
    PaymentIntent.objects.filter(
        metadata__backfilled_from='financial_transaction.mpesa_*').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0007_providerevent_tenant'),
        ('ledger', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(backfill, unbackfill),
    ]
