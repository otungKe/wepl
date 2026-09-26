from django.contrib import admin

from apps.core.admin_readonly import ReadOnlyAdminMixin
from .models import MpesaSTKRequest, MpesaC2BTransaction


@admin.register(MpesaSTKRequest)
class MpesaSTKRequestAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    # Rail records are written by the callback path only; the admin is a viewer.
    list_display = ('phone_number', 'amount', 'status', 'mpesa_receipt', 'contribution', 'created_at')
    list_filter = ('status',)
    search_fields = ('phone_number', 'mpesa_receipt', 'checkout_request_id')


@admin.register(MpesaC2BTransaction)
class MpesaC2BTransactionAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    # The record is read-only. force_reconcile stays because nothing in the ops
    # console replaces it yet: it re-runs the same automatic match the callback
    # ran (fund from the WEPL-<id> reference, member from the phone), so it
    # cannot choose who is credited or how much.
    list_display = ('phone_number', 'amount', 'mpesa_receipt', 'bill_ref_number', 'is_reconciled', 'created_at')
    list_filter = ('is_reconciled',)
    search_fields = ('phone_number', 'mpesa_receipt', 'bill_ref_number')
    actions = ['force_reconcile']

    def force_reconcile(self, request, queryset):
        from .services import MpesaService
        reconciled = 0
        for tx in queryset.filter(is_reconciled=False):
            if MpesaService.reconcile_c2b(tx):
                reconciled += 1
        self.message_user(request, f"Reconciled {reconciled} transaction(s).")
    force_reconcile.short_description = "Force reconcile selected transactions"
