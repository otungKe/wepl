from django.contrib import admin

from .models import OutboxEvent


@admin.action(description='Re-queue selected events for delivery')
def requeue_events(modeladmin, request, queryset):
    """Reset selected events to PENDING and kick the relay to deliver them."""
    from apps.core.tasks import process_outbox
    queryset.update(status=OutboxEvent.Status.PENDING, last_error='', attempts=0)
    process_outbox.delay()


@admin.register(OutboxEvent)
class OutboxEventAdmin(admin.ModelAdmin):
    list_display  = ('id', 'event_type', 'status', 'attempts', 'created_at', 'processed_at')
    list_filter   = ('status', 'event_type')
    search_fields = ('id', 'event_type')
    readonly_fields = ('id', 'event_type', 'payload', 'created_at', 'processed_at', 'last_error')
    ordering      = ('-created_at',)
    actions       = [requeue_events]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        # Read-only; status changes happen only via the requeue action.
        return False
