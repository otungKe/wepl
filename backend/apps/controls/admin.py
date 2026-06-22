from django.contrib import admin
from django.utils import timezone
from unfold.admin import ModelAdmin

from .models import ControlDecision, HeldMovement, LimitRule


@admin.action(description='Release selected (clear the hold)')
def release_movements(modeladmin, request, queryset):
    n = queryset.filter(status=HeldMovement.Status.OPEN).update(
        status=HeldMovement.Status.RELEASED, reviewed_by=request.user, reviewed_at=timezone.now(),
    )
    modeladmin.message_user(request, f"{n} movement(s) released. Re-initiate the original action to proceed.")


@admin.action(description='Reject selected')
def reject_movements(modeladmin, request, queryset):
    n = queryset.filter(status=HeldMovement.Status.OPEN).update(
        status=HeldMovement.Status.REJECTED, reviewed_by=request.user, reviewed_at=timezone.now(),
    )
    modeladmin.message_user(request, f"{n} movement(s) rejected.")


@admin.register(HeldMovement)
class HeldMovementAdmin(ModelAdmin):
    list_display  = ('created_at', 'status', 'decision', 'op_type', 'amount', 'subject_user', 'recipient_phone', 'reason')
    list_filter   = ('status', 'decision', 'op_type', 'created_at')
    search_fields = ('subject_user__phone_number', 'recipient_phone', 'idempotency_key', 'reason')
    date_hierarchy = 'created_at'
    actions = [release_movements, reject_movements]
    readonly_fields = (
        'created_at', 'decision', 'op_type', 'direction', 'amount', 'subject_user',
        'recipient_phone', 'idempotency_key', 'context_type', 'context_id', 'rule', 'reason',
        'reviewed_by', 'reviewed_at',
    )

    def has_add_permission(self, request):
        return False


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
