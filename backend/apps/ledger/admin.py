from django.contrib import admin

from apps.core.admin_readonly import ReadOnlyAdminMixin
from .models import (
    Account,
    AccountBalance,
    ExchangeRate,
    FinancialTransaction,
    JournalEntry,
    JournalLine,
)


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display  = ('base_currency', 'quote_currency', 'rate', 'effective_at', 'source')
    list_filter   = ('base_currency', 'quote_currency')
    search_fields = ('base_currency', 'quote_currency', 'source')
    date_hierarchy = 'effective_at'


@admin.register(FinancialTransaction)
class FinancialTransactionAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    # Rail columns left the ledger in ADR-0030; the receipt and the correlation
    # id are on the PaymentIntent, which the ops console shows through the
    # money-activity seam. Django admin searches the intent by relation.
    list_display  = ('id', 'op_type', 'state', 'amount', 'initiated_by', 'recipient_phone',
                     'context_type', 'context_id', 'created_at')
    list_filter   = ('op_type', 'state')
    search_fields = ('idempotency_key', 'payment_intents__receipt',
                     'payment_intents__provider_ref',
                     'initiated_by__phone_number')
    # Read-only: execute_payout pays ft.amount to ft.recipient_phone, so an
    # editable form here would be a way to redirect a payout.
    ordering = ('-created_at',)


# ── Double-entry core ───────────────────────────────────────────────────────

@admin.register(Account)
class AccountAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display  = ('code', 'name', 'type', 'parent', 'owner', 'fund_type', 'fund_id', 'is_active')
    list_filter   = ('type', 'fund_type', 'is_active')
    search_fields = ('code', 'name', 'owner__phone_number')
    # Read-only: accounts are opened by the chart of accounts (coa.py) and are
    # referenced by immutable lines.
    ordering = ('code',)


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
class AccountBalanceAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    # Projection maintained by the posting writer; rebuilt from lines, never edited.
    list_display  = ('account', 'debit_total', 'credit_total', 'updated_at')
    search_fields = ('account__code',)
