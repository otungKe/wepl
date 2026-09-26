from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.core.admin_readonly import ReadOnlyAdminMixin

from .models import ControlDecision, HeldMovement, LimitRule


@admin.register(HeldMovement)
class HeldMovementAdmin(ReadOnlyAdminMixin, ModelAdmin):
    # Read-only. A hold is released by deciding its EDD case (ops console →
    # verification.decide_subject_case → controls.cases), which also issues the
    # ControlOverride the customer's retry needs. The old admin action flipped the
    # status without an override, so it closed the hold and still blocked the retry.
    list_display  = ('created_at', 'status', 'decision', 'op_type', 'amount', 'subject_user', 'recipient_phone', 'reason')
    list_filter   = ('status', 'decision', 'op_type', 'created_at')
    search_fields = ('subject_user__phone_number', 'recipient_phone', 'idempotency_key', 'reason')
    date_hierarchy = 'created_at'


@admin.register(LimitRule)
class LimitRuleAdmin(ModelAdmin):
    list_display  = ('name', 'scope', 'direction', 'op_type', 'period', 'max_amount', 'max_count', 'action', 'priority', 'is_active')
    list_filter   = ('scope', 'direction', 'period', 'action', 'is_active')
    list_editable = ('is_active', 'priority')
    search_fields = ('name',)


@admin.register(ControlDecision)
class ControlDecisionAdmin(ModelAdmin):
    list_display  = ('created_at', 'decision', 'op_type', 'direction', 'amount', 'subject_user', 'rule', 'reason')
    list_filter   = ('decision', 'direction', 'op_type', 'created_at')
    search_fields = ('reason', 'subject_user__phone_number')
    date_hierarchy = 'created_at'
    readonly_fields = tuple(f.name for f in ControlDecision._meta.fields)

    def has_add_permission(self, request):
        return False  # append-only audit log

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
