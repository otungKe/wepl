# PaymentIntent hardening (post-MVP): structured failure, lifecycle timestamps,
# provider-ref/receipt uniqueness, ProviderEvent history, expanded drift kinds.
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def copy_failure_and_backfill_initiated(apps, schema_editor):
    """Preserve the old free-text failure_reason into the new failure_message, and
    seed initiated_at from created_at for existing rows."""
    PaymentIntent = apps.get_model("payments", "PaymentIntent")
    for pi in PaymentIntent.objects.all().iterator():
        changed = []
        old = getattr(pi, "failure_reason", "") or ""
        if old and not pi.failure_message:
            pi.failure_message = old
            changed.append("failure_message")
        if pi.initiated_at is None:
            pi.initiated_at = pi.created_at
            changed.append("initiated_at")
        if changed:
            pi.save(update_fields=changed)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("ledger", "0015_financialtransaction_counterparty_name"),
        ("payments", "0005_delete_legacy_payment"),
        ("tenants", "0005_extend_rls_policies"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── ProviderEvent (append-only provider callback history) ──────────────
        migrations.CreateModel(
            name="ProviderEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("provider", models.CharField(db_index=True, max_length=30)),
                ("provider_ref", models.CharField(blank=True, db_index=True, default="", max_length=255)),
                ("event_type", models.CharField(
                    help_text="e.g. collection_callback, payout_result, c2b_confirmation.",
                    max_length=40)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("signature_verified", models.BooleanField(
                    default=False,
                    help_text="Did the event pass the provider's authenticity check (IP/HMAC)?")),
                ("provider_event_id", models.CharField(
                    blank=True, default="",
                    help_text="The provider's own event id, when it supplies one (for dedup/replay).",
                    max_length=128)),
                ("received_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={"ordering": ["-received_at"]},
        ),
        # ── PaymentIntent: add the new fields FIRST (so the copy has a target) ──
        migrations.AddField(
            model_name="paymentintent", name="callback_received_at",
            field=models.DateTimeField(blank=True, null=True,
                                       help_text="When the settling provider callback landed.")),
        migrations.AddField(
            model_name="paymentintent", name="failure_code",
            field=models.CharField(
                blank=True, default="", max_length=64,
                help_text="Provider/normalised failure code for analytics & retry classification.")),
        migrations.AddField(
            model_name="paymentintent", name="failure_message",
            field=models.TextField(blank=True, default="")),
        migrations.AddField(
            model_name="paymentintent", name="initiated_at",
            field=models.DateTimeField(blank=True, null=True,
                                       help_text="When the provider accepted initiation.")),
        migrations.AddField(
            model_name="paymentintent", name="provider_completed_at",
            field=models.DateTimeField(blank=True, null=True,
                                       help_text="When the provider reached a terminal result.")),
        # ── Migrate data, THEN drop the old field ──────────────────────────────
        migrations.RunPython(copy_failure_and_backfill_initiated, noop),
        migrations.RemoveField(model_name="paymentintent", name="failure_reason"),
        # ── State-only alters ──────────────────────────────────────────────────
        migrations.AlterField(
            model_name="paymentintent", name="currency",
            field=models.CharField(default="KES", editable=False, max_length=3)),
        migrations.AlterField(
            model_name="paymentintent", name="direction",
            field=models.CharField(
                choices=[("collection", "Collection (pay-in)"), ("payout", "Payout (pay-out)")],
                help_text="Provider money-flow axis (pay-in vs pay-out); not the business op — see op_type.",
                max_length=12)),
        migrations.AlterField(
            model_name="paymentintent", name="op_type",
            field=models.CharField(
                blank=True, default="", max_length=30,
                help_text="Denormalised business-op label for analytics; not a dependency, not authoritative.")),
        migrations.AlterField(
            model_name="reconciliationdrift", name="kind",
            field=models.CharField(
                choices=[
                    ("stuck_pending_intent", "Stuck pending intent"),
                    ("intent_ft_mismatch", "Intent/FinancialTransaction state mismatch"),
                    ("ft_without_journal", "Successful FT without a posted journal"),
                    ("ft_stuck_processing", "FinancialTransaction stuck in processing"),
                    ("amount_mismatch", "Intent/FinancialTransaction amount mismatch"),
                    ("duplicate_receipt", "Provider receipt seen on more than one intent"),
                    ("duplicate_callback", "Duplicate provider callback"),
                    ("provider_timeout", "Provider timed out with no result"),
                    ("missing_callback", "Initiated payment with no callback"),
                    ("provider_success_ledger_failure", "Provider succeeded but ledger did not"),
                    ("ledger_success_provider_failure", "Ledger succeeded but provider did not"),
                    ("orphan_provider_txn", "Provider transaction with no intent"),
                    ("late_callback", "Callback arrived after the grace window"),
                ],
                db_index=True, max_length=40)),
        # ── Uniqueness constraints ─────────────────────────────────────────────
        migrations.AddConstraint(
            model_name="paymentintent",
            constraint=models.UniqueConstraint(
                condition=models.Q(("provider_ref", ""), _negated=True),
                fields=("provider", "provider_ref"),
                name="uniq_provider_ref_per_provider")),
        migrations.AddConstraint(
            model_name="paymentintent",
            constraint=models.UniqueConstraint(
                condition=models.Q(("receipt", ""), _negated=True),
                fields=("receipt",),
                name="uniq_provider_receipt")),
        # ── ProviderEvent FK + indexes + dedup constraint ──────────────────────
        migrations.AddField(
            model_name="providerevent", name="payment_intent",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="provider_events", to="payments.paymentintent")),
        migrations.AddIndex(
            model_name="providerevent",
            index=models.Index(fields=["provider", "provider_ref"], name="pe_provider_ref_idx")),
        migrations.AddIndex(
            model_name="providerevent",
            index=models.Index(fields=["payment_intent", "received_at"], name="pe_intent_received_idx")),
        migrations.AddConstraint(
            model_name="providerevent",
            constraint=models.UniqueConstraint(
                condition=models.Q(("provider_event_id", ""), _negated=True),
                fields=("provider", "provider_event_id"),
                name="uniq_provider_event_id")),
    ]
