from django.contrib import admin

from .models import OutboxEvent


@admin.action(description='Re-queue selected events for delivery')
def requeue_events(modeladmin, request, queryset):
    from apps.core.tasks import deliver_outbox_event
    queryset.update(status=OutboxEvent.Status.PENDING, error='', attempts=0)
    for event_id in queryset.values_list('id', flat=True):
        deliver_outbox_event.delay(str(event_id))


@admin.register(OutboxEvent)
class OutboxEventAdmin(admin.ModelAdmin):
    list_display  = ('id', 'event_type', 'status', 'attempts', 'created_at', 'processed_at')
    list_filter   = ('status', 'event_type')
    search_fields = ('id', 'event_type')
    readonly_fields = ('id', 'event_type', 'payload', 'created_at', 'processed_at', 'error')
    ordering      = ('-created_at',)
    actions       = [requeue_events]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        # Allow status changes only (via action); prevent field edits
        return False
