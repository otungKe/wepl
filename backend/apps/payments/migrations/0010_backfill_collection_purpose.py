"""Carry what each pay-in is for from the STK request onto its PaymentIntent.

A settled pay-in is now routed from the intent (``purpose`` / ``subject_ref``)
rather than from the M-Pesa rail record, whose foreign keys into contributions
are what kept the rail app tied to the domain. Before those keys can be dropped
in a later deploy, every intent that can settle has to carry the same answer —
additive first (P-7/E-2).

Pending intents matter most: a callback that lands after this deploy settles
through the intent. Settled ones are filled too, so reporting and any replay read
one source. Rows without a matching STK request are left blank; the callback
falls back to the rail record for those, exactly as before.

Re-runnable: only intents whose ``purpose`` is still blank are touched.
"""
from django.db import migrations

COLLECTION = 'collection'

# payment_type → the STK request field holding the target's id.
_SUBJECT_FIELD = {
    'contribution': 'contribution_id',
    'welfare': 'welfare_fund_id',
    'shares': 'shares_fund_id',
    'advance_repayment': 'advance_id',
}


def backfill(apps, schema_editor):
    PaymentIntent = apps.get_model('payments', 'PaymentIntent')
    MpesaSTKRequest = apps.get_model('mpesa', 'MpesaSTKRequest')

    intents = (PaymentIntent.objects
               .filter(direction=COLLECTION, purpose='')
               .exclude(provider_ref='')
               .order_by('pk'))
    for intent in intents.iterator(chunk_size=500):
        stk = (MpesaSTKRequest.objects
               .filter(checkout_request_id=intent.provider_ref)
               .first())
        if stk is None:
            continue
        field = _SUBJECT_FIELD.get(stk.payment_type)
        subject = getattr(stk, field) if field else None
        if subject is None:
            continue
        # A queryset write, so updated_at keeps its real value.
        PaymentIntent.objects.filter(pk=intent.pk).update(
            purpose=stk.payment_type, subject_ref=str(subject))


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0009_collection_purpose'),
        ('mpesa', '0004_mpesac2btransaction_first_name_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
