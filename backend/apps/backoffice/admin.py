"""
Django admin for provisioning Back Office operators.

Only a Platform Admin (Django superuser) manages these. Operators cannot reset
their own password from the console — a reset is an admin action here that issues
a one-time temporary password and forces a change on next login.
"""
from django.contrib import admin, messages
from unfold.admin import ModelAdmin as UnfoldModelAdmin

from .models import StaffAccount


@admin.action(description="Reset password (issue a one-time temp password)")
def reset_staff_password(modeladmin, request, queryset):
    for staff in queryset:
        temp = staff.force_reset()
        modeladmin.message_user(
            request,
            f"{staff.email}: temporary password — {temp} — share securely; "
            f"the operator must change it on next sign-in.",
            level=messages.WARNING,
        )


@admin.register(StaffAccount)
class StaffAccountAdmin(UnfoldModelAdmin):
    list_display = ("email", "full_name", "role_list", "is_active", "is_superuser",
                    "must_change_password", "last_login")
    list_filter = ("is_active", "is_superuser", "must_change_password", "groups")
    search_fields = ("email", "full_name")
    ordering = ("email",)
    filter_horizontal = ("groups",)
    readonly_fields = ("last_login", "password_changed_at", "created_at", "updated_at")
    actions = [reset_staff_password]

    fieldsets = (
        (None, {"fields": ("email", "full_name", "is_active")}),
        ("Access", {"fields": ("is_superuser", "groups")}),
        ("Password", {"fields": ("must_change_password", "password_changed_at"),
                      "description": "Use the “Reset password” action to issue a temporary "
                                     "password. Operators set their own password on first sign-in."}),
        ("Meta", {"fields": ("created_by", "last_login", "created_at", "updated_at")}),
    )

    @admin.display(description="Roles")
    def role_list(self, obj):
        return ", ".join(g.name.replace("ops:", "") for g in obj.groups.all()) or "—"

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = getattr(request.user, "phone_number", "") or str(request.user)
            if not obj.has_usable_password():
                # New account with no password yet — issue a temp so they can log in.
                temp = obj.force_reset() if obj.pk else None
                super().save_model(request, obj, form, change)
                if temp is None:
                    temp = obj.force_reset()
                self.message_user(
                    request,
                    f"{obj.email}: temporary password — {temp} — share securely; "
                    f"the operator must change it on first sign-in.",
                    level=messages.WARNING,
                )
                return
        super().save_model(request, obj, form, change)
