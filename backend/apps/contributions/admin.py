from django.contrib import admin
from .models import (
    Contribution,
    ContributionParticipant,
    ContributionTransaction,
    ROSCASlot,
    DisbursementRequest,
    DisbursementVote,
    WelfareFund,
    WelfareClaim,
    EmergencyAdvance,
)


@admin.register(Contribution)
class ContributionAdmin(admin.ModelAdmin):
    list_display = ('title', 'contribution_type', 'visibility', 'current_amount', 'target_amount', 'is_active', 'created_at')
    list_filter = ('contribution_type', 'visibility', 'is_active')
    search_fields = ('title',)


@admin.register(ContributionParticipant)
class ContributionParticipantAdmin(admin.ModelAdmin):
    list_display = ('user', 'contribution', 'is_active', 'joined_at')
    list_filter = ('is_active',)


@admin.register(ContributionTransaction)
class ContributionTransactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'contribution', 'amount', 'transaction_type', 'note', 'created_at')
    list_filter = ('transaction_type',)


@admin.register(ROSCASlot)
class ROSCASlotAdmin(admin.ModelAdmin):
    list_display = ('contribution', 'cycle_number', 'slot_order', 'participant', 'has_received', 'payout_amount')
    list_filter = ('has_received',)


@admin.register(DisbursementRequest)
class DisbursementRequestAdmin(admin.ModelAdmin):
    list_display = ('contribution', 'requested_by', 'amount', 'status', 'created_at')
    list_filter = ('status',)


@admin.register(DisbursementVote)
class DisbursementVoteAdmin(admin.ModelAdmin):
    list_display = ('request', 'voter', 'vote', 'voted_at')


@admin.register(WelfareFund)
class WelfareFundAdmin(admin.ModelAdmin):
    list_display = ('community', 'name', 'balance', 'monthly_contribution')


@admin.register(WelfareClaim)
class WelfareClaimAdmin(admin.ModelAdmin):
    list_display = ('claimant', 'fund', 'amount_requested', 'status', 'created_at')
    list_filter = ('status',)
    actions = ['force_disburse']

    def force_disburse(self, request, queryset):
        from .services import WelfareService
        for claim in queryset.filter(status='APPROVED'):
            WelfareService._disburse(claim)
        self.message_user(request, "Selected claims disbursed.")
    force_disburse.short_description = "Force disburse approved claims"


@admin.register(EmergencyAdvance)
class EmergencyAdvanceAdmin(admin.ModelAdmin):
    list_display = ('borrower', 'contribution', 'amount', 'interest_rate', 'status', 'repayment_due')
    list_filter = ('status',)
