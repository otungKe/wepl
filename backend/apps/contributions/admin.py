from django.contrib import admin

from apps.core.admin_readonly import ReadOnlyAdminMixin
from .models import (
    Contribution,
    ContributionParticipant,
    ROSCASlot,
    DisbursementRequest,
    DisbursementVote,
    WelfareFund,
    WelfareClaim,
    EmergencyAdvance,
)

# Group money records are read-only here: every change is a governed act (votes,
# approvals, post_journal) that runs through apps.contributions.services.


@admin.register(Contribution)
class ContributionAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ('title', 'contribution_type', 'visibility', 'pool_balance', 'target_amount', 'is_active', 'created_at')
    list_filter = ('contribution_type', 'visibility', 'is_active')
    search_fields = ('title',)

    @admin.display(description='Pool balance')
    def pool_balance(self, obj):
        from apps.ledger.balances import fund_balance
        return fund_balance('contribution', obj.id)


@admin.register(ContributionParticipant)
class ContributionParticipantAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ('user', 'contribution', 'is_active', 'joined_at')
    list_filter = ('is_active',)


@admin.register(ROSCASlot)
class ROSCASlotAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ('contribution', 'cycle_number', 'slot_order', 'participant', 'has_received', 'payout_amount')
    list_filter = ('has_received',)


@admin.register(DisbursementRequest)
class DisbursementRequestAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ('contribution', 'requested_by', 'amount', 'status', 'created_at')
    list_filter = ('status',)


@admin.register(DisbursementVote)
class DisbursementVoteAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ('request', 'voter', 'vote', 'voted_at')


@admin.register(WelfareFund)
class WelfareFundAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ('community', 'name', 'fund_balance', 'monthly_contribution')

    @admin.display(description='Balance')
    def fund_balance(self, obj):
        from apps.ledger.balances import fund_balance
        return fund_balance('welfare', obj.id)


@admin.register(WelfareClaim)
class WelfareClaimAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ('claimant', 'fund', 'amount_requested', 'status', 'created_at')
    list_filter = ('status',)


@admin.register(EmergencyAdvance)
class EmergencyAdvanceAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ('borrower', 'contribution', 'amount', 'interest_rate', 'status', 'repayment_due')
    list_filter = ('status',)
