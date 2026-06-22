from django.contrib import admin

from .models import CrossTenantAccessAttempt, Tenant


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display  = ('name', 'slug', 'is_active', 'created_at')
    list_filter   = ('is_active',)
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(CrossTenantAccessAttempt)
class CrossTenantAccessAttemptAdmin(admin.ModelAdmin):
    list_display  = ('created_at', 'user', 'current_tenant', 'resource_type', 'resource_id', 'resource_tenant', 'path')
    list_filter   = ('resource_type', 'created_at')
    search_fields = ('resource_id', 'path', 'user__phone_number')
    date_hierarchy = 'created_at'
    readonly_fields = tuple(f.name for f in CrossTenantAccessAttempt._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
