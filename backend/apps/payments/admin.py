from django.contrib import admin

from .models import PaymentIntent, ProviderEvent, ReconciliationDrift


@admin.register(PaymentIntent)
class PaymentIntentAdmin(admin.ModelAdmin):
    list_display  = ('created_at', 'provider', 'direction', 'status', 'amount',
                     'provider_ref', 'receipt', 'failure_code', 'financial_transaction')
    list_filter   = ('provider', 'direction', 'status', 'created_at')
    search_fields = ('provider_ref', 'receipt', 'idempotency_key', 'failure_code')
    date_hierarchy = 'created_at'
    # Status only ever moves through transition_to(); never hand-edit it in admin.
    readonly_fields = ('status', 'created_at', 'updated_at',
                       'initiated_at', 'callback_received_at', 'provider_completed_at')


@admin.register(ProviderEvent)
class ProviderEventAdmin(admin.ModelAdmin):
    """Read-only view of the append-only provider callback history."""
    list_display  = ('received_at', 'provider', 'event_type', 'provider_ref',
                     'signature_verified', 'payment_intent')
    list_filter   = ('provider', 'event_type', 'signature_verified', 'received_at')
    search_fields = ('provider_ref', 'provider_event_id')
    date_hierarchy = 'received_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ReconciliationDrift)
class ReconciliationDriftAdmin(admin.ModelAdmin):
    list_display  = ('detected_at', 'kind', 'subject_type', 'subject_id', 'resolved_at')
    list_filter   = ('kind', 'resolved_at', 'detected_at')
    search_fields = ('subject_id', 'detail')
    date_hierarchy = 'detected_at'
    actions = ['mark_resolved']

    @admin.action(description="Mark selected drifts resolved")
    def mark_resolved(self, request, queryset):
        from django.utils import timezone
        queryset.filter(resolved_at__isnull=True).update(resolved_at=timezone.now())
