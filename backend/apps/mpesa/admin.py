from django.contrib import admin
from .models import MpesaSTKRequest, MpesaC2BTransaction


@admin.register(MpesaSTKRequest)
class MpesaSTKRequestAdmin(admin.ModelAdmin):
    list_display = ('phone_number', 'amount', 'status', 'mpesa_receipt', 'contribution', 'created_at')
    list_filter = ('status',)
    search_fields = ('phone_number', 'mpesa_receipt', 'checkout_request_id')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(MpesaC2BTransaction)
class MpesaC2BTransactionAdmin(admin.ModelAdmin):
    list_display = ('phone_number', 'amount', 'mpesa_receipt', 'bill_ref_number', 'is_reconciled', 'created_at')
    list_filter = ('is_reconciled',)
    search_fields = ('phone_number', 'mpesa_receipt', 'bill_ref_number')
    readonly_fields = ('created_at',)
    actions = ['force_reconcile']

    def force_reconcile(self, request, queryset):
        from .services import MpesaService
        reconciled = 0
        for tx in queryset.filter(is_reconciled=False):
            if MpesaService.reconcile_c2b(tx):
                reconciled += 1
        self.message_user(request, f"Reconciled {reconciled} transaction(s).")
    force_reconcile.short_description = "Force reconcile selected transactions"
