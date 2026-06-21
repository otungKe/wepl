from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import ControlDecision, LimitRule


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
