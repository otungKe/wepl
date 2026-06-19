from django.contrib import admin
from .models import (
    Account,
    AccountBalance,
    FinancialTransaction,
    JournalEntry,
    JournalLine,
)


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


# ── Double-entry core ───────────────────────────────────────────────────────

@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display  = ('code', 'name', 'type', 'parent', 'owner', 'fund_type', 'fund_id', 'is_active')
    list_filter   = ('type', 'fund_type', 'is_active')
    search_fields = ('code', 'name', 'owner__phone_number')
    readonly_fields = ('created_at',)
    ordering = ('code',)

    def has_delete_permission(self, request, obj=None):
        return False  # accounts are referenced by immutable lines


class JournalLineInline(admin.TabularInline):
    model = JournalLine
    extra = 0
    can_delete = False
    readonly_fields = ('account', 'direction', 'amount', 'note', 'created_at')

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display  = ('id', 'op_type', 'posted_at', 'financial_transaction', 'reverses', 'created_by', 'created_at')
    list_filter   = ('op_type',)
    search_fields = ('idempotency_key', 'narration')
    readonly_fields = tuple(f.name for f in JournalEntry._meta.get_fields() if not f.is_relation or f.many_to_one)
    inlines = (JournalLineInline,)
    ordering = ('-created_at',)

    def has_add_permission(self, request):
        return False  # only via posting.post_journal()

    def has_change_permission(self, request, obj=None):
        return False  # immutable

    def has_delete_permission(self, request, obj=None):
        return False  # immutable


@admin.register(JournalLine)
class JournalLineAdmin(admin.ModelAdmin):
    list_display  = ('id', 'journal', 'account', 'direction', 'amount', 'created_at')
    list_filter   = ('direction',)
    search_fields = ('account__code', 'journal__idempotency_key')
    ordering = ('-created_at',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False  # immutable

    def has_delete_permission(self, request, obj=None):
        return False  # immutable


@admin.register(AccountBalance)
class AccountBalanceAdmin(admin.ModelAdmin):
    list_display  = ('account', 'debit_total', 'credit_total', 'updated_at')
    search_fields = ('account__code',)
    readonly_fields = ('account', 'debit_total', 'credit_total', 'updated_at')

    def has_add_permission(self, request):
        return False  # projection maintained by the posting writer

    def has_delete_permission(self, request, obj=None):
        return False
