from django.contrib import admin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    """Strictly read-only — the audit log is append-only (ADR-0019)."""
    list_display  = ("created_at", "action", "actor_label", "target_type", "target_id", "tenant")
    list_filter   = ("action", "target_type", "created_at")
    search_fields = ("actor_label", "target_id", "request_id", "action")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
