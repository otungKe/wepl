from django.contrib import admin
from .models import FinancialTransaction, LedgerEntry


@admin.register(FinancialTransaction)
class FinancialTransactionAdmin(admin.ModelAdmin):
    list_display  = ('id', 'op_type', 'state', 'amount', 'initiated_by', 'recipient_phone',
                     'context_type', 'context_id', 'mpesa_receipt', 'created_at')
    list_filter   = ('op_type', 'state')
    search_fields = ('idempotency_key', 'mpesa_receipt', 'mpesa_conversation_id',
                     'initiated_by__phone_number')
    readonly_fields = ('idempotency_key', 'created_at', 'updated_at')
    ordering = ('-created_at',)

    def has_delete_permission(self, request, obj=None):
        return False  # financial records must never be deleted


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display  = ('id', 'entry_type', 'direction', 'amount', 'user',
                     'contribution', 'mpesa_receipt', 'created_at')
    list_filter   = ('entry_type', 'direction')
    search_fields = ('idempotency_key', 'mpesa_receipt', 'user__phone_number')
    readonly_fields = tuple(f.name for f in LedgerEntry._meta.get_fields())
    ordering = ('-created_at',)

    def has_add_permission(self, request):
        return False  # ledger entries only created via write_ledger_entry()

    def has_change_permission(self, request, obj=None):
        return False  # immutable

    def has_delete_permission(self, request, obj=None):
        return False  # immutable
