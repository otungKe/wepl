from django.contrib import admin

from .models import PaymentIntent, ReconciliationDrift


@admin.register(PaymentIntent)
class PaymentIntentAdmin(admin.ModelAdmin):
    list_display  = ('created_at', 'provider', 'direction', 'status', 'amount',
                     'provider_ref', 'financial_transaction')
    list_filter   = ('provider', 'direction', 'status', 'created_at')
    search_fields = ('provider_ref', 'receipt', 'idempotency_key')
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at', 'updated_at')


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
